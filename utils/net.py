"""HTTP transport, header interpolation and server-response unwrapping."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from utils.config import PLACEHOLDERS, api_url, app_config, auth_token, retry_times, timeout_seconds


def lookup_ref(config: Mapping[str, Any], path: str) -> Any:
    node: Any = config
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def interpolate(text: str, config: Mapping[str, Any]) -> str:
    """Expand ``${dotted.path}`` references against the whole config.

    Missing or placeholder targets expand to ``""``, so a template header whose
    value is not filled yet is simply dropped rather than sent literally.
    """

    def replace(match: re.Match[str]) -> str:
        node = lookup_ref(config, match.group(1))
        if node is None:
            return ""
        value = str(node)
        return "" if value.strip() in PLACEHOLDERS else value

    return re.sub(r"\$\{([^{}]+)\}", replace, text)


def configured_headers(config: Mapping[str, Any]) -> dict[str, str]:
    """Forward a caller-supplied session context from config["request"]["headers"].

    Header values may reference the rest of the config via ``${dotted.path}``
    (e.g. ``"Cookie": "${auth.cookie}"``).  Only headers that resolve to a real,
    non-placeholder value are forwarded, so the committed template stays inert
    until the user fills the matching field.  This lets the user replay their
    own logged-in App/WebView session context (Cookie / Origin / Referer)
    without code changes.
    """
    request = config.get("request", {})
    headers = request.get("headers", {}) if isinstance(request, Mapping) else {}
    if not isinstance(headers, Mapping):
        return {}
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        text = "" if value is None else str(value)
        resolved = interpolate(text, config)
        if not resolved or resolved.strip() in PLACEHOLDERS:
            continue
        forwarded[key] = resolved
    return forwarded


def login_hint(raw: bytes) -> str:
    """Actionable hint when a server error page says the session is not logged in.

    The school backend rejects requests that carry only a page ``token`` but no
    authenticated SSO session Cookie (observed as ``RuntimeException: 请先登录``
    with an HTML 500 page).  We never echo the page body; we only map marker
    text to an instruction.
    """
    if not raw:
        return ""
    text: str | None = None
    for encoding in ("utf-8", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    markers = ("请先登录", "请登录", "未登录", "登录后操作", "先登录", "not logged", "login first")
    if any(marker in text for marker in markers):
        return "，服务端判定当前会话未登录：仅 token 不够，请在签到时段把本人已登录的 App/浏览器会话 Cookie 填入 data.json→auth.cookie"
    return ""


def request_json(
    config: Mapping[str, Any], endpoint: str, method: str, body: Any | None = None, query: Mapping[str, Any] | None = None
) -> Any:
    url = api_url(config, endpoint)
    if query:
        url = f"{url}?{urlencode(query, doseq=True)}"
    headers = {
        "Accept": "application/json",
        "User-Agent": str(app_config(config).get("user_agent", "Mozilla/5.0")),
        "token": auth_token(config),
    }
    headers.update(configured_headers(config))
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    attempts = retry_times(config)
    last_error: ValueError | None = None
    for attempt in range(1, attempts + 1):
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=timeout_seconds(config)) as response:
                raw = response.read(4 * 1024 * 1024)
                try:
                    return json.loads(raw.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    content_type = response.headers.get("Content-Type", "")
                    hint = "（响应是 HTML/非 JSON，通常是服务端会话异常，而非协议错误）" if "html" in content_type.lower() else ""
                    raise ValueError(
                        f"{endpoint} 返回了非 JSON 响应 (Content-Type: {content_type or 'unknown'}){hint}{login_hint(raw)}"
                    ) from None
        except HTTPError as exc:
            try:
                snippet = exc.read(131072)
            except Exception:
                snippet = b""
            content_type = str(exc.headers.get("Content-Type", "")) if exc.headers else ""
            suffix = f"，响应 Content-Type: {content_type or 'unknown'}" if content_type else ""
            html = "，服务端返回了 HTML 错误页（多为会话/鉴权层异常）" if "html" in content_type.lower() else ""
            last_error = ValueError(f"{endpoint} 返回 HTTP {exc.code}{suffix}{html}{login_hint(snippet)}")
            last_error.__cause__ = exc
            if login_hint(snippet) or exc.code not in {502, 503, 504}:
                raise last_error from exc
        except URLError as exc:
            last_error = ValueError(f"{endpoint} 网络错误: {exc.reason}")
            last_error.__cause__ = exc
        except ValueError:
            raise
        if attempt < attempts:
            time.sleep(min(attempt, 3))
    assert last_error is not None
    raise last_error


def unwrap_success(payload: Any, endpoint: str) -> Any:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{endpoint} 响应不是 JSON 对象")
    if payload.get("success") is not True or payload.get("code") != 1:
        message = payload.get("msg") or "服务端返回失败"
        raise ValueError(f"{endpoint}: {message}")
    return payload.get("data")
