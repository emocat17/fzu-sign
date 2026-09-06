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
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


# This module lives at <root>/utils/analysis/, so the repo root is three levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402  (root module, added to sys.path above)
from utils.config import save_user_auth, save_user_cookie, user_configs, validate_user_config  # noqa: E402
from utils.notification import format_summary  # noqa: E402
from utils.net import configured_headers, request_json  # noqa: E402
from utils.sso import (  # noqa: E402
    encrypt_password,
    extract_token,
    parse_login_page,
    session_unauthenticated,
)


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
                code, status = main.run(config, send=False)
        self.assertEqual(code, 0)
        self.assertEqual(status, "preview")
        self.assertIn("DRY-RUN", output.getvalue())
        self.assertIn("协议预览", output.getvalue())

    def test_send_path_stops_when_init_shows_already_signed(self):
        init = json.loads(json.dumps(_INIT_OK))
        init["data"]["paramsData"].update({"FStartTime": "00:00", "FEndTime": "23:59"})
        with _JsonServer(
            {
                "init.action": (200, init),
                "currentTimestamp.action": (200, {"success": True, "code": 1, "data": {"timestamp": 0}}),
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            config["request"] = {"enabled": True}
            output = io.StringIO()
            with redirect_stdout(output):
                code, status = main.run(config, send=True)
        self.assertEqual(code, 0)
        self.assertEqual(status, "already_signed")
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
            output = io.StringIO()
            with redirect_stdout(output):
                code, status = main.run(config, send=True)
        self.assertEqual(code, 0)
        self.assertEqual(status, "session_ok")
        self.assertIn("不在签到时间窗口内", output.getvalue())

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
                code, status = main.run(config, send=True)
        self.assertEqual(code, 0)
        self.assertEqual(status, "success")
        self.assertIn("旗山校区", output.getvalue())
        self.assertIn("clockIn.action", output.getvalue())

    def test_request_enabled_is_the_single_send_switch(self):
        # Plain `python main.py` signs in iff request.enabled is exactly true.
        self.assertFalse(main.should_auto_send({"request": {"enabled": False}}))
        self.assertFalse(main.should_auto_send({"request": {"enabled": "true"}}))
        self.assertFalse(main.should_auto_send({"request": {}}))
        self.assertFalse(main.should_auto_send({}))
        self.assertTrue(main.should_auto_send({"request": {"enabled": True}}))
        self.assertFalse(main.should_auto_send({"request": {"enabled": True}, "enabled": False}))


class MultiUserConfigTests(unittest.TestCase):
    def test_legacy_single_user_config_still_works(self):
        configs = user_configs(_base_config("http://127.0.0.1:1"))
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["auth"]["token"], "test-token")

    def test_users_inherit_shared_app_and_keep_own_auth_location(self):
        root = {
            "app": {"base_url": "https://example.test", "user_agent": "ua"},
            "request": {"enabled": True, "headers": {"Cookie": "${auth.cookie}"}},
            "encryption": {"key": "apexinfoapexinfo", "iv": "apexinfoapexinfo"},
            "WXKey": "shared-key",
            "users": [
                {
                    "name": "张三",
                    "auth": {"token": "t1", "cookie": "c1"},
                    "location": {"latitude": "1", "longitude": "2", "address": "A"},
                },
                {
                    "name": "李四",
                    "auth": {"token": "t2", "cookie": "c2"},
                    "location": {"latitude": "3", "longitude": "4", "address": "B"},
                },
            ],
        }
        configs = user_configs(root)
        self.assertEqual([item["name"] for item in configs], ["张三", "李四"])
        self.assertEqual(configs[0]["app"]["base_url"], "https://example.test")
        self.assertEqual(configs[1]["WXKey"], "shared-key")
        self.assertEqual(configs[0]["auth"]["token"], "t1")
        self.assertEqual(configs[1]["location"]["address"], "B")
        self.assertEqual([item["name"] for item in user_configs(root, "李四")], ["李四"])

    def test_main_runs_each_user_and_can_filter_by_name(self):
        calls: list[str] = []

        def fake_run(config, send, path=None):
            calls.append(config["name"])
            return 0, "preview"

        root = {
            "app": {"base_url": "http://127.0.0.1:1"},
            "request": {"enabled": False},
            "users": [
                {"name": "张三", "auth": {"token": "t1"}, "location": {"latitude": 1, "longitude": 2, "address": "A"}},
                {"name": "李四", "auth": {"token": "t2"}, "location": {"latitude": 3, "longitude": 4, "address": "B"}},
            ],
        }
        with mock.patch.object(main, "load_config", return_value=root), mock.patch.object(main, "run", side_effect=fake_run):
            self.assertEqual(main.main(["--dry-run"]), 0)
            self.assertEqual(calls, ["张三", "李四"])
            calls.clear()
            self.assertEqual(main.main(["--dry-run", "--user", "李四"]), 0)
            self.assertEqual(calls, ["李四"])

    def test_disabled_user_is_skipped(self):
        root = {
            "app": {"base_url": "http://127.0.0.1:1"},
            "request": {"enabled": True},
            "users": [
                {"name": "张三", "enabled": False, "auth": {"token": "t1"}, "location": {"latitude": 1, "longitude": 2, "address": "A"}},
            ],
        }
        with mock.patch.object(main, "load_config", return_value=root), mock.patch.object(main, "run") as run:
            self.assertEqual(main.main([]), 0)
            run.assert_not_called()


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
            configured_headers(config),
            {"Cookie": "session=abc", "token": "t-1", "X-Runtime": "7"},
        )

    def test_configured_headers_empty_when_no_request_headers(self):
        self.assertEqual(configured_headers({"request": {"headers": {}}}), {})


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
                request_json(config, "init.action", "POST", body={})
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
                request_json(config, "init.action", "POST", body={})
        self.assertIn("非 JSON", str(ctx.exception))


class SessionCheckTests(unittest.TestCase):
    def test_check_session_ok_does_not_notify(self):
        with _JsonServer(
            {
                "init.action": (200, _INIT_OK),
                "currentTimestamp.action": (200, _TIMESTAMP_OK),
            }
        ) as server:
            config = _base_config(f"http://127.0.0.1:{server.port}")
            output = io.StringIO()
            with mock.patch.object(main, "notify_signed") as notify, redirect_stdout(output):
                code, reason, refreshed = main.check_session(config)
        self.assertEqual(code, 0)
        self.assertEqual(reason, "")
        self.assertFalse(refreshed)
        self.assertIn("会话有效", output.getvalue())
        notify.assert_not_called()

    def test_check_session_notifies_when_login_required(self):
        config = _base_config("http://127.0.0.1:1")
        boom = ValueError("init.action 返回 HTTP 500 … 服务端判定当前会话未登录：仅 token 不够…")
        err = io.StringIO()
        with mock.patch("utils.protocol.fetch_init", side_effect=boom), mock.patch.object(
            main, "notify_signed"
        ) as notify, redirect_stderr(err):
            code, reason, refreshed = main.check_session(config)
        self.assertEqual(code, 2)
        self.assertEqual(reason, "cookie错误")
        self.assertFalse(refreshed)
        self.assertIn("会话异常", err.getvalue())
        notify.assert_called_once()
        text = notify.call_args[0][1]
        self.assertIn("会话失效", text)

    def test_check_session_skips_notify_on_network_error(self):
        config = _base_config("http://127.0.0.1:1")
        boom = ValueError("init.action 网络错误: timed out")
        with mock.patch("utils.protocol.fetch_init", side_effect=boom), mock.patch.object(
            main, "notify_signed"
        ) as notify:
            code, reason, refreshed = main.check_session(config)
        self.assertEqual(code, 2)
        self.assertEqual(reason, "网络超时")
        self.assertFalse(refreshed)
        notify.assert_not_called()

    def test_missing_cookie_logs_in_before_first_request(self):
        config = _base_config("http://127.0.0.1:1")
        config["name"] = "张三"
        config["auth"] = {"username": "u1", "password": "p1", "token": "test-token"}
        with mock.patch("utils.protocol.fetch_init", return_value=_INIT_OK["data"]), mock.patch(
            "utils.protocol.fetch_server_timestamp", return_value=1
        ), mock.patch.object(main, "login_and_session", return_value=("JSESSIONID=new", "tok-new")) as login, mock.patch.object(
            main, "save_user_auth"
        ):
            code, reason, refreshed = main.check_session(config)
        self.assertEqual(code, 0)
        self.assertEqual(reason, "")
        self.assertTrue(refreshed)
        login.assert_called_once()
        self.assertEqual(config["auth"]["cookie"], "JSESSIONID=new")
        self.assertEqual(config["auth"]["token"], "tok-new")

    def test_check_session_refreshes_cookie_when_credentials_present(self):
        config = _base_config("http://127.0.0.1:1")
        config["name"] = "张三"
        config["auth"] = {"username": "u1", "password": "p1", "token": "test-token", "cookie": "old"}
        boom = ValueError("init.action 返回 HTTP 500 … 服务端判定当前会话未登录：仅 token 不够…")
        with mock.patch("utils.protocol.fetch_init", side_effect=[boom, _INIT_OK["data"]]), mock.patch(
            "utils.protocol.fetch_server_timestamp", return_value=1
        ), mock.patch.object(main, "login_and_session", return_value=("JSESSIONID=new", "tok-new")) as login, mock.patch.object(
            main, "save_user_auth"
        ) as save, mock.patch.object(main, "notify_signed") as notify:
            code, reason, refreshed = main.check_session(config)
        self.assertEqual(code, 0)
        self.assertEqual(reason, "")
        self.assertTrue(refreshed)
        login.assert_called_once()
        save.assert_called_once()
        self.assertEqual(config["auth"]["cookie"], "JSESSIONID=new")
        self.assertEqual(config["auth"]["token"], "tok-new")
        notify.assert_not_called()


class SsoHelperTests(unittest.TestCase):
    def test_parse_login_page_reads_croypto_and_flowkey(self):
        html = """
        <p id="login-croypto">QwjGJXuyxqUJi0ZxZlqqgA==</p>
        <p id="login-page-flowkey">abc_flow</p>
        <p id="captchaId"></p>
        <p id="sso-second"></p>
        <p id="login-error-code"></p>
        """
        page = parse_login_page(html)
        self.assertEqual(page["croypto"], "QwjGJXuyxqUJi0ZxZlqqgA==")
        self.assertEqual(page["execution"], "abc_flow")

    def test_encrypt_password_is_aes_ecb_base64(self):
        key = "QwjGJXuyxqUJi0ZxZlqqgA=="
        cipher = encrypt_password("secret", key)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        import base64

        raw = base64.b64decode(cipher)
        decryptor = Cipher(algorithms.AES(base64.b64decode(key)), modes.ECB()).decryptor()
        padded = decryptor.update(raw) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        self.assertEqual(plain.decode("utf-8"), "secret")

    def test_session_unauthenticated_detects_login_markers(self):
        self.assertTrue(session_unauthenticated(ValueError("服务端判定当前会话未登录")))
        self.assertFalse(session_unauthenticated(ValueError("网络错误: timed out")))

    def test_save_user_cookie_updates_only_that_user(self):
        import tempfile

        payload = {
            "users": [
                {"name": "张三", "auth": {"cookie": "old-1", "token": "t1"}},
                {"name": "other", "auth": {"cookie": "old-2", "token": "t2"}},
            ]
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            save_user_cookie(path, "张三", "JSESSIONID=new")
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["users"][0]["auth"]["cookie"], "JSESSIONID=new")
        self.assertEqual(saved["users"][0]["auth"]["token"], "t1")
        self.assertEqual(saved["users"][1]["auth"]["cookie"], "old-2")

    def test_extract_token_from_url_and_html(self):
        self.assertEqual(
            extract_token("https://yzsxg.fzu.edu.cn/plug-in/livecloud/project/fzu/attn/index.action?token=abc123&contextPath="),
            "abc123",
        )
        self.assertEqual(extract_token("https://example.test/", 'href="index.action?token=xyz789"'), "xyz789")

    def test_save_user_auth_updates_cookie_and_token(self):
        import tempfile

        payload = {"users": [{"name": "张三", "auth": {"cookie": "old", "token": "old-t"}}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            save_user_auth(path, "张三", "JSESSIONID=new", "tok-new")
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["users"][0]["auth"]["cookie"], "JSESSIONID=new")
        self.assertEqual(saved["users"][0]["auth"]["token"], "tok-new")


class SummaryAndValidationTests(unittest.TestCase):
    def test_format_summary_session_probe_is_not_sign_in_success(self):
        title, desp = format_summary(
            [
                {"name": "张三", "status": "session_ok", "reason": "会话有效（未到签到窗口）"},
            ]
        )
        self.assertEqual(title, "会话探活完成")
        self.assertIn("张三成功", desp)
        title, desp = format_summary(
            [
                {"name": "张三", "status": "refreshed", "reason": "已刷新Cookie/token"},
            ]
        )
        self.assertEqual(title, "Cookie 已刷新")

    def test_format_summary_all_success(self):
        title, desp = format_summary(
            [
                {"name": "张三", "status": "success"},
                {"name": "李四", "status": "already_signed", "reason": "已签到"},
            ]
        )
        self.assertEqual(title, "全部签到成功")
        self.assertIn("张三成功", desp)
        self.assertIn("李四成功", desp)

    def test_format_summary_partial_failure_with_reason(self):
        title, desp = format_summary(
            [
                {"name": "张三", "status": "success"},
                {"name": "李四", "status": "failed", "reason": "cookie错误"},
            ]
        )
        self.assertEqual(title, "部分失败")
        self.assertIn("李四失败，原因：cookie错误", desp)

    def test_validate_user_config_requires_token_or_login(self):
        with self.assertRaises(ValueError):
            validate_user_config({"name": "张三", "auth": {"token": ""}, "location": {"latitude": 1, "longitude": 2, "address": "A"}})
        validate_user_config(
            {
                "name": "张三",
                "auth": {"username": "u", "password": "p"},
                "location": {"latitude": 1, "longitude": 2, "address": "A"},
            }
        )

    def test_classify_reason_cookie(self):
        self.assertEqual(main.classify_reason(ValueError("服务端判定当前会话未登录")), "cookie错误")
        self.assertEqual(main.classify_reason(ValueError("init.action 网络错误: timed out")), "网络超时")

    def test_refresh_cookie_flag_skips_sign_in(self):
        root = {
            "app": {"base_url": "http://127.0.0.1:1"},
            "request": {"enabled": True},
            "users": [
                {
                    "name": "张三",
                    "auth": {"username": "u", "password": "p", "token": "t1"},
                    "location": {"latitude": 1, "longitude": 2, "address": "A"},
                }
            ],
        }
        with mock.patch.object(main, "load_config", return_value=root), mock.patch.object(
            main, "refresh_session_cookie"
        ) as refresh, mock.patch.object(main, "run") as run:
            self.assertEqual(main.main(["--refresh-cookie"]), 0)
            refresh.assert_called_once()
            run.assert_not_called()
            refresh.assert_called_once()
            self.assertTrue(refresh.call_args.kwargs.get("notify"))


if __name__ == "__main__":
    unittest.main()
