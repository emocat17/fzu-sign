#!/usr/bin/env python3
"""Configuration-driven request runner for an authorized check-in workflow.

The APK contains only the generic service launcher.  The actual remote
check-in endpoint must therefore be supplied in the JSON configuration after
it has been observed from an account and service environment the caller is
authorized to use.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_CONFIG_PATH = Path(__file__).with_name("late_rollcall_config.json")
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH"}
ALLOWED_BODY_ENCODINGS = {"json", "form", "raw"}
FULL_PLACEHOLDER = re.compile(r"^\$\{([^{}]+)\}$")
EMBEDDED_PLACEHOLDER = re.compile(r"\$\{([^{}]+)\}")
SECRET_MARKERS = (
    "token",
    "password",
    "passwd",
    "cookie",
    "authorization",
    "secret",
)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def load_config(path: Path) -> dict[str, Any]:
    """Load and minimally validate a JSON configuration file."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at {path}:{exc.lineno}:{exc.colno}") from exc
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a JSON object")
    request = value.get("request", {})
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")
    method = str(request.get("method", "POST")).upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"request.method must be one of {sorted(ALLOWED_METHODS)}")
    return value


def _resolve_path(context: Mapping[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            raise ValueError(f"unresolved configuration placeholder: ${{{path}}}")
    return deepcopy(current)


def render_value(value: Any, context: Mapping[str, Any]) -> Any:
    """Recursively replace ``${section.field}`` placeholders.

    A string made solely of one placeholder keeps the referenced JSON type,
    so coordinates and IDs can remain numbers when the server expects them.
    Placeholders embedded in larger strings are rendered as text.
    """

    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    whole = FULL_PLACEHOLDER.fullmatch(value)
    if whole:
        return _resolve_path(context, whole.group(1))

    def replace(match: re.Match[str]) -> str:
        resolved = _resolve_path(context, match.group(1))
        if isinstance(resolved, (dict, list)):
            return json.dumps(resolved, ensure_ascii=False, separators=(",", ":"))
        return str(resolved)

    return EMBEDDED_PLACEHOLDER.sub(replace, value)


def _with_query(url: str, query: Mapping[str, Any]) -> str:
    if not query:
        return url
    parts = urlsplit(url)
    existing = parse_qsl(parts.query, keep_blank_values=True)
    extra: list[tuple[str, Any]] = []
    for key, value in query.items():
        if isinstance(value, list):
            extra.extend((key, item) for item in value)
        else:
            extra.append((key, value))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(existing + extra), parts.fragment)
    )


def build_request(config: Mapping[str, Any]) -> Request:
    """Build one HTTP request from the configured request template."""

    request_config = config.get("request")
    if not isinstance(request_config, Mapping):
        raise ValueError("request must be a JSON object")
    url = render_value(request_config.get("url", ""), config)
    if not isinstance(url, str) or not url.strip():
        raise ValueError("request.url is empty; fill it with the verified check-in URL")
    url = _with_query(url, render_value(request_config.get("query", {}), config))
    method = str(request_config.get("method", "POST")).upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"unsupported request method: {method}")

    rendered_headers = render_value(request_config.get("headers", {}), config)
    if not isinstance(rendered_headers, Mapping):
        raise ValueError("request.headers must be a JSON object")
    headers = {str(key): str(value) for key, value in rendered_headers.items()}
    for key, value in headers.items():
        if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
            raise ValueError(f"newline is not allowed in HTTP header {key!r}")

    body = render_value(request_config.get("body"), config)
    body_encoding = str(request_config.get("body_encoding", "json")).casefold()
    if body_encoding not in ALLOWED_BODY_ENCODINGS:
        raise ValueError(f"unsupported request.body_encoding: {body_encoding}")
    data: bytes | None = None
    if body is not None:
        if body_encoding == "json":
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            default_content_type = "application/json"
        elif body_encoding == "form":
            if not isinstance(body, Mapping):
                raise ValueError("form request.body must be a JSON object")
            data = urlencode(body, doseq=True).encode("utf-8")
            default_content_type = "application/x-www-form-urlencoded"
        else:
            if not isinstance(body, str):
                raise ValueError("raw request.body must be a string")
            data = body.encode("utf-8")
            default_content_type = "text/plain; charset=utf-8"
        if not any(key.casefold() == "content-type" for key in headers):
            headers["Content-Type"] = default_content_type
    return Request(url, data=data, headers=headers, method=method)


def should_send(config: Mapping[str, Any], send_flag: bool) -> bool:
    """Return whether a real request is allowed by both config and CLI."""

    if not send_flag:
        return False
    request = config.get("request", {})
    if not isinstance(request, Mapping):
        raise ValueError("request must be a JSON object")
    if request.get("enabled", True) is not True:
        raise ValueError("request.enabled is false; review the request and set it to true first")
    if not str(request.get("url", "")).strip():
        raise ValueError("request.url is empty; fill it with the verified check-in URL")
    return True


def redact_config(value: Any, key: str = "") -> Any:
    """Return a printable copy with credential-bearing values removed."""

    if any(marker in key.casefold() for marker in SECRET_MARKERS):
        if value in (None, ""):
            return value
        return "***REDACTED***"
    if isinstance(value, dict):
        return {item_key: redact_config(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_config(item, key) for item in value]
    return value


def redact_url(url: str) -> str:
    """Mask credential-like query parameters for log output only."""

    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    safe_pairs = []
    for key, value in pairs:
        if any(marker in key.casefold() for marker in SECRET_MARKERS):
            value = "***REDACTED***"
        safe_pairs.append((key, value))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(safe_pairs), parts.fragment)
    )


def _print_inventory(config: Mapping[str, Any]) -> None:
    app = config.get("app", {})
    if isinstance(app, Mapping):
        print("已确认入口:")
        for key in ("public_h5_url", "late_rollcall_entry_url", "scheme", "service_deep_link"):
            if app.get(key):
                print(f"  {key}: {render_value(app[key], config)}")
    discovery = config.get("service_discovery", {})
    if isinstance(discovery, Mapping):
        candidates = discovery.get("candidate_paths", [])
        if candidates:
            print("服务目录候选路径（不是已确认签到提交 URL）:")
            for item in candidates:
                print(f"  {item}")
    inventory = config.get("field_inventory", {})
    if isinstance(inventory, Mapping):
        print("字段清单:")
        for category, fields in inventory.items():
            if isinstance(fields, list):
                print(f"  {category}: {', '.join(map(str, fields))}")


def _print_request(request: Request, body_limit: int = 12000) -> None:
    print(f"请求预览: {request.get_method()} {redact_url(request.full_url)}")
    safe_headers = redact_config(dict(request.header_items()))
    print("请求头:")
    print(json.dumps(safe_headers, ensure_ascii=False, indent=2))
    if request.data is not None:
        body = request.data.decode("utf-8", "replace")
        content_type = next(
            (value for key, value in request.header_items() if key.casefold() == "content-type"),
            "",
        )
        if "application/x-www-form-urlencoded" in content_type.casefold():
            pairs = parse_qsl(body, keep_blank_values=True)
            safe_pairs = [
                (
                    key,
                    "***REDACTED***"
                    if any(marker in key.casefold() for marker in SECRET_MARKERS)
                    else value,
                )
                for key, value in pairs
            ]
            body = urlencode(safe_pairs)
        else:
            try:
                body_value: Any = json.loads(body)
                body = json.dumps(redact_config(body_value), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                body = "<non-JSON body omitted>"
        print("请求体:")
        print(body[:body_limit])


def _send(request: Request, timeout: float) -> int:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(64 * 1024)
            text = raw.decode("utf-8", "replace")
            print(f"响应: HTTP {response.status}")
            try:
                print(json.dumps(json.loads(text), ensure_ascii=False, indent=2)[:20000])
            except json.JSONDecodeError:
                print(text[:20000])
            return 0
    except HTTPError as exc:
        raw = exc.read(16 * 1024).decode("utf-8", "replace")
        print(f"HTTP 错误: {exc.code} {exc.reason}", file=sys.stderr)
        print(raw[:4000], file=sys.stderr)
        return 2
    except URLError as exc:
        print(f"网络错误: {exc.reason}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a configured authorized check-in request")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--send", action="store_true", help="explicitly send the configured request")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        _print_inventory(config)
        if not should_send(config, args.send):
            print("\nDRY-RUN：未发送任何网络请求。")
            if str(config.get("request", {}).get("url", "")).strip():
                _print_request(build_request(config))
            else:
                print("真实签到请求尚未配置：请在 JSON 中填入自有账号抓到的 URL、headers 和 body。")
            return 0
        request = build_request(config)
        _print_request(request)
        print("\n已收到 --send 且配置启用，准备发送一次请求。")
        return _send(request, float(config.get("timeout_seconds", 20)))
    except (ValueError, TypeError, KeyError) as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
