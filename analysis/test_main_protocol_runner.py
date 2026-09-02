"""Tests for the dedicated protocol runner ``main.py``.

These guard regressions codex's earlier suite did not cover: the dry-run
preview path (which previously referenced an undefined ``check_data`` and would
raise NameError the moment ``init.action`` succeeded), header interpolation of
``${dotted.path}`` references, and clean surfacing of non-JSON / HTTP 5xx
server responses instead of raw tracebacks.
"""

import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402  (root module, added to sys.path above)


def _base_config(server_url: str) -> dict:
    """Config that points the runner at a local test server, no secrets."""
    return {
        "app": {"base_url": server_url, "user_agent": "test-agent"},
        "auth": {"token": "test-token"},
        "location": {"latitude": 26.05, "longitude": 119.19, "address": "测试地址"},
        "clock_in": {"caIsNo": "0"},
        "request": {"headers": {}},
        "encryption": {"key": "apexinfoapexinfo", "iv": "apexinfoapexinfo"},
    }


class _JsonServer:
    """Tiny threaded JSON responder for read-only endpoint fakes."""

    def __init__(self, responses):
        routes = responses  # endpoint-suffix -> (status, body-dict/str/bytes)

        class Handler(BaseHTTPRequestHandler):
            def _handle(self):
                body_bytes = None
                content_length = int(self.headers.get("Content-Length", 0) or 0)
                if content_length:
                    body_bytes = self.rfile.read(content_length)
                path_no_query = self.path.split("?", 1)[0].rstrip("/")
                for suffix, (status, payload) in routes.items():
                    if path_no_query.endswith(suffix):
                        if isinstance(payload, (dict, list)):
                            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        elif isinstance(payload, str):
                            raw = payload.encode("utf-8")
                        else:
                            raw = payload
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                        return
                raw = b"not found"
                self.send_response(404)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_PUT = _handle  # noqa: N815

            def log_message(self, *_args):
                return

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self.thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self._httpd.shutdown()
        self.thread.join(timeout=2)
        self._httpd.server_close()


_INIT_OK = {
    "success": True,
    "code": 1,
    "data": {
        "paramsData": {"FStartTime": "21:30", "FEndTime": "23:59", "FLateTime": "23:00"},
        "schoolData": [{"ID": "2", "FName": "旗山校区", "FPosition": '{"range": []}'}],
        "userData": {"FDefaultCampus": "2", "FCollUnit": 7, "FWay": 1},
        "statusData": {"status": "PROCESSING"},
    },
}
_TIMESTAMP_OK = {"success": True, "code": 1, "data": {"timestamp": 1788379200000}}


class MainDryRunTests(unittest.TestCase):
    def test_preview_path_runs_without_undefined_variable(self):
        """print_preview must not reference check_data (regression guard)."""
        output = io.StringIO()
        with redirect_stdout(output):
            main.print_preview(_base_config("http://127.0.0.1:1"), _INIT_OK["data"], 1788379200000)
        text = output.getvalue()
        self.assertIn("协议预览", text)
        self.assertIn("clockIn fields", text)
        self.assertNotIn("check_data", text)

    def test_read_only_run_against_local_server_prints_preview_and_exits_zero(self):
        with _JsonServer(
            {
                "init.action": (200, _INIT_OK),
                "currentTimestamp.action": (200, _TIMESTAMP_OK),
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main.run(config, send=False)
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN", output.getvalue())
        self.assertIn("协议预览", output.getvalue())

    def test_send_path_stops_when_init_shows_already_signed(self):
        with _JsonServer(
            {
                "init.action": (200, _INIT_OK),
                "currentTimestamp.action": (200, _TIMESTAMP_OK),
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            config["request"] = {"enabled": True}
            output = io.StringIO()
            with redirect_stdout(output):
                code = main.run(config, send=True)
        self.assertEqual(code, 0)
        self.assertIn("服务端已显示签到成功", output.getvalue())

    def test_send_path_refuses_outside_time_window(self):
        # A not-yet-signed status plus an epoch timestamp (outside 21:30-23:59)
        # must abort before any real submission is attempted.
        init = json.loads(json.dumps(_INIT_OK))  # deep copy
        init["data"]["statusData"] = {"status": "UNSIGNED"}
        with _JsonServer(
            {
                "init.action": (200, init),
                "currentTimestamp.action": (200, {"success": True, "code": 1, "data": {"timestamp": 0}}),
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            config["request"] = {"enabled": True}
            with self.assertRaises(ValueError) as ctx:
                main.run(config, send=True)
        self.assertIn("不在服务端返回的签到时间窗口", str(ctx.exception))

    def test_send_submits_matched_campus_and_exits_zero(self):
        # In-window, not-yet-signed account with request.enabled=true: plain
        # send must run check.action, use the matched campus for clockIn, and
        # submit without any interactive prompt.
        init = json.loads(json.dumps(_INIT_OK))
        init["data"]["statusData"] = {"status": "UNSIGNED"}
        init["data"]["paramsData"].update({"FStartTime": "00:00", "FEndTime": "23:59"})
        check_ok = {
            "success": True,
            "code": 1,
            "data": [{"id": "2", "title": "旗山校区"}],
        }
        clock_ok = {"success": True, "code": 1, "data": {"attn": "ok"}}
        with _JsonServer(
            {
                "init.action": (200, init),
                "currentTimestamp.action": (200, {"success": True, "code": 1, "data": {"timestamp": 0}}),
                "check.action": (200, check_ok),
                "clockIn.action": (200, clock_ok),
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            config["request"] = {"enabled": True}
            output = io.StringIO()
            with redirect_stdout(output):
                code = main.run(config, send=True)
        self.assertEqual(code, 0)
        self.assertIn("旗山校区", output.getvalue())
        self.assertIn("clockIn.action", output.getvalue())

    def test_request_enabled_is_the_single_send_switch(self):
        # Plain `python main.py` signs in iff request.enabled is exactly true.
        self.assertFalse(main.should_auto_send({"request": {"enabled": False}}))
        self.assertFalse(main.should_auto_send({"request": {"enabled": "true"}}))
        self.assertFalse(main.should_auto_send({"request": {}}))
        self.assertFalse(main.should_auto_send({}))
        self.assertTrue(main.should_auto_send({"request": {"enabled": True}}))


class MainHeaderTests(unittest.TestCase):
    def test_configured_headers_interpolate_refs_and_drop_placeholders(self):
        config = {
            "auth": {"cookie": "session=abc", "token": "t-1", "origin": ""},
            "app": {"user_agent": "ua-1"},
            "request": {
                "headers": {
                    "Cookie": "${auth.cookie}",
                    "Origin": "${auth.origin}",
                    "Referer": "XXXXX",
                    "token": "${auth.token}",
                    "X-Runtime": "7",
                }
            },
        }
        self.assertEqual(
            main.configured_headers(config),
            {"Cookie": "session=abc", "token": "t-1", "X-Runtime": "7"},
        )

    def test_configured_headers_empty_when_no_request_headers(self):
        self.assertEqual(main.configured_headers({"request": {"headers": {}}}), {})


class MainErrorReportingTests(unittest.TestCase):
    def test_http_500_html_is_reported_as_value_error_without_body_leak(self):
        html_body = "<html><body>server error session</body></html>".encode("utf-8")

        class _Html500Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_body)

            def log_message(self, *_args):
                return

        server = HTTPServer(("127.0.0.1", 0), _Html500Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = _base_config(f"http://127.0.0.1:{server.server_port}")
            with self.assertRaises(ValueError) as ctx:
                main.request_json(config, "init.action", "POST", body={})
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        message = str(ctx.exception)
        self.assertIn("HTTP 500", message)
        self.assertIn("HTML", message)
        self.assertNotIn("server error", message)  # body never echoed

    def test_http_200_but_non_json_body_reported_cleanly(self):
        with _JsonServer(
            {
                "init.action": (
                    200,
                    b"<html>this is not json, it is an html error page served as 200</html>",
                )
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            with self.assertRaises(ValueError) as ctx:
                main.request_json(config, "init.action", "POST", body={})
        self.assertIn("非 JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
