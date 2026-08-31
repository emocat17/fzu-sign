import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from late_rollcall_checkin import (
    _print_inventory,
    _send,
    build_request,
    load_config,
    redact_config,
    should_send,
)


class ConfigAndRequestTests(unittest.TestCase):
    def test_renders_nested_body_and_headers_from_json_context(self):
        config = {
            "request": {
                "url": "https://example.invalid/check/${service.service_id}",
                "method": "POST",
                "headers": {"token": "${auth.token}"},
                "body": {
                    "userId": "${identity.user_id}",
                    "latitude": "${location.latitude}",
                },
            },
            "auth": {"token": "token-value"},
            "identity": {"user_id": "u-1"},
            "location": {"latitude": 26.06},
            "service": {"service_id": "svc-1"},
        }

        request = build_request(config)

        self.assertEqual(request.full_url, "https://example.invalid/check/svc-1")
        self.assertEqual(request.get_header("Token"), "token-value")
        self.assertEqual(
            json.loads(request.data),
            {"userId": "u-1", "latitude": 26.06},
        )

    def test_dry_run_does_not_require_send_permission(self):
        config = {
            "request": {
                "url": "https://example.invalid",
                "method": "POST",
                "body": {},
            }
        }

        self.assertFalse(should_send(config, send_flag=False))

    def test_send_requires_explicit_flag_and_nonempty_endpoint(self):
        config = {
            "request": {
                "url": "https://example.invalid",
                "method": "POST",
                "body": {},
            }
        }

        self.assertTrue(should_send(config, send_flag=True))
        config["request"]["url"] = ""
        with self.assertRaises(ValueError):
            should_send(config, send_flag=True)

    def test_builds_form_encoded_body_when_capture_is_not_json(self):
        request = build_request(
            {
                "request": {
                    "url": "https://example.invalid/check",
                    "method": "POST",
                    "body_encoding": "form",
                    "body": {"id": "${service.service_id}", "ok": "1"},
                },
                "service": {"service_id": "svc-1"},
            }
        )

        self.assertEqual(request.data, b"id=svc-1&ok=1")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")


class RootConfigTests(unittest.TestCase):
    def test_root_config_separates_confirmed_urls_and_capture_fields(self):
        config = load_config(PROJECT_ROOT / "late_rollcall_config.json")

        self.assertEqual(config["app"]["scheme"], "kysk-fdxy-app")
        self.assertEqual(
            config["app"]["public_h5_url"],
            "https://app.fzu.edu.cn/fd-app/m/index.html",
        )
        self.assertEqual(
            config["app"]["late_rollcall_entry_url"],
            "https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action",
        )
        self.assertEqual(config["service"]["entry_url"], config["app"]["late_rollcall_entry_url"])
        self.assertEqual(config["service"]["service_url"], config["app"]["late_rollcall_entry_url"])
        self.assertEqual(config["request"]["body"], {})
        self.assertIn("serviceId", config["service"]["known_field_candidates"])
        self.assertIn("latitude", config["location"]["known_field_candidates"])
        self.assertFalse(config["request"]["enabled"])

    def test_inventory_prints_late_rollcall_entry_url(self):
        config = {
            "app": {
                "late_rollcall_entry_url": "https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action"
            }
        }
        output = io.StringIO()
        with redirect_stdout(output):
            _print_inventory(config)
        self.assertIn(config["app"]["late_rollcall_entry_url"], output.getvalue())


class OutputSafetyTests(unittest.TestCase):
    def test_redacts_credential_bearing_keys_recursively(self):
        value = {
            "token": "secret-token",
            "password": "secret-password",
            "Cookie": "session=secret",
            "nested": {"Authorization": "Bearer secret"},
            "userId": "u-1",
        }

        safe = redact_config(value)

        self.assertEqual(safe["token"], "***REDACTED***")
        self.assertEqual(safe["password"], "***REDACTED***")
        self.assertEqual(safe["Cookie"], "***REDACTED***")
        self.assertEqual(safe["nested"]["Authorization"], "***REDACTED***")
        self.assertEqual(safe["userId"], "u-1")

    def test_http_error_reports_status_without_printing_secret_header(self):
        class ErrorHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
                self.send_response(400, "Bad Request")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"invalid request"}')

            def log_message(self, *_args):
                return

        server = HTTPServer(("127.0.0.1", 0), ErrorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = build_request(
                {
                    "request": {
                        "url": f"http://127.0.0.1:{server.server_port}/check",
                        "method": "POST",
                        "headers": {"X-Secret-Header": "do-not-print"},
                        "body": {},
                    }
                }
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = _send(request, timeout=2)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertEqual(result, 2)
        self.assertIn("HTTP 错误: 400", stderr.getvalue())
        self.assertNotIn("do-not-print", stdout.getvalue() + stderr.getvalue())

    def test_request_preview_redacts_secret_query_values(self):
        from late_rollcall_checkin import _print_request

        request = build_request(
            {
                "request": {
                    "url": "https://example.invalid/check?token=secret-token&ok=1",
                    "method": "POST",
                    "body": {},
                }
            }
        )
        output = io.StringIO()
        with redirect_stdout(output):
            _print_request(request)

        self.assertNotIn("secret-token", output.getvalue())
        self.assertIn("ok=1", output.getvalue())

    def test_request_preview_shows_form_fields(self):
        from late_rollcall_checkin import _print_request

        request = build_request(
            {
                "request": {
                    "url": "https://example.invalid/check",
                    "method": "POST",
                    "body_encoding": "form",
                    "body": {"id": "svc-1", "note": "ok"},
                }
            }
        )
        output = io.StringIO()
        with redirect_stdout(output):
            _print_request(request)

        self.assertIn("id=svc-1", output.getvalue())
        self.assertIn("note=ok", output.getvalue())


if __name__ == "__main__":
    unittest.main()
