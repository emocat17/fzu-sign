#!/usr/bin/env python3
"""Authorized late-rollcall protocol runner.

Default mode performs read-only init/time requests and prints a redacted
preview. Final clock-in submission is disabled unless both the JSON switch and
the explicit ``--send`` flag are enabled, followed by an action-time
confirmation. This runner does not fabricate location or bypass server checks.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError as exc:  # pragma: no cover - exercised only on missing dependency
    raise SystemExit(
        "缺少 cryptography 依赖，请运行: python -m pip install cryptography"
    ) from exc


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "data.json"
H5_AES_KEY = "apexinfoapexinfo"
H5_PATH_PREFIX = "/livecloud/project/fzu/attn/"
PLACEHOLDERS = {"", "XXXXX", "<redacted>", "<runtime>", "<actual>"}
CONFIRM_WORD = "CONFIRM"


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"配置文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式错误: {path}:{exc.lineno}:{exc.colno}") from exc
    if not isinstance(value, dict):
        raise ValueError("配置根节点必须是 JSON 对象")
    return value


def real_value(value: Any, field: str) -> Any:
    if value is None or (isinstance(value, str) and value.strip() in PLACEHOLDERS):
        raise ValueError(f"请填写 {field}，不能使用 XXXXX")
    return value


def app_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = config.get("app", {})
    if not isinstance(value, Mapping):
        raise ValueError("app 必须是 JSON 对象")
    return value


def auth_token(config: Mapping[str, Any]) -> str:
    auth = config.get("auth", {})
    if not isinstance(auth, Mapping):
        raise ValueError("auth 必须是 JSON 对象")
    return str(real_value(auth.get("token"), "auth.token"))


def base_url(config: Mapping[str, Any]) -> str:
    app = app_config(config)
    return str(app.get("base_url", "https://yzsxg.fzu.edu.cn")).rstrip("/")


def api_url(config: Mapping[str, Any], endpoint: str) -> str:
    prefix = str(app_config(config).get("path_prefix", H5_PATH_PREFIX)).strip("/")
    return f"{base_url(config)}/{prefix}/{endpoint.lstrip('/')}"


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
    request = Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urlopen(request, timeout=float(config.get("timeout_seconds", 20))) as response:
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
            snippet = exc.read(131072)  # scan for login markers; never printed
        except Exception:
            snippet = b""
        content_type = str(exc.headers.get("Content-Type", "")) if exc.headers else ""
        suffix = f"，响应 Content-Type: {content_type or 'unknown'}" if content_type else ""
        html = "，服务端返回了 HTML 错误页（多为会话/鉴权层异常）" if "html" in content_type.lower() else ""
        raise ValueError(f"{endpoint} 返回 HTTP {exc.code}{suffix}{html}{login_hint(snippet)}") from exc
    except URLError as exc:
        raise ValueError(f"{endpoint} 网络错误: {exc.reason}") from exc


def unwrap_success(payload: Any, endpoint: str) -> Any:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{endpoint} 响应不是 JSON 对象")
    if payload.get("success") is not True or payload.get("code") != 1:
        message = payload.get("msg") or "服务端返回失败"
        raise ValueError(f"{endpoint}: {message}")
    return payload.get("data")


def fetch_init(config: Mapping[str, Any]) -> Mapping[str, Any]:
    data = unwrap_success(request_json(config, "init.action", "POST", body={}), "init.action")
    if not isinstance(data, Mapping):
        raise ValueError("init.action data 不是对象")
    return data


def fetch_server_timestamp(config: Mapping[str, Any]) -> int:
    data = unwrap_success(request_json(config, "currentTimestamp.action", "GET"), "currentTimestamp.action")
    if not isinstance(data, Mapping):
        raise ValueError("currentTimestamp.action data 不是对象")
    value = data.get("timestamp")
    if not isinstance(value, (int, float)):
        raise ValueError("currentTimestamp.action 缺少数字 timestamp")
    return int(value)


def parse_time(value: Any, field: str) -> tuple[int, int]:
    text = str(real_value(value, field))
    try:
        hour, minute = (int(item) for item in text.split(":", 1))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field} 必须是 HH:MM") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{field} 超出时间范围")
    return hour, minute


def in_time_window(server_timestamp: int, start: Any, end: Any) -> bool:
    start_hour, start_minute = parse_time(start, "paramsData.FStartTime")
    end_hour, end_minute = parse_time(end, "paramsData.FEndTime")
    current = datetime.fromtimestamp(server_timestamp / 1000)
    now_minutes = current.hour * 60 + current.minute
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    if start_minutes <= end_minutes:
        return start_minutes <= now_minutes <= end_minutes
    return now_minutes >= start_minutes or now_minutes <= end_minutes


def is_late(server_timestamp: int, late_time: Any) -> int:
    if late_time in (None, ""):
        return 0
    hour, minute = parse_time(late_time, "paramsData.FLateTime")
    current = datetime.fromtimestamp(server_timestamp / 1000)
    return int(current.hour * 60 + current.minute > hour * 60 + minute)


def school_rows(init_data: Mapping[str, Any]) -> list[tuple[str, str]]:
    rows = init_data.get("schoolData", [])
    if not isinstance(rows, list):
        return []
    result: list[tuple[str, str]] = []
    for row in rows:
        if isinstance(row, Mapping) and row.get("ID") is not None:
            result.append((str(row["ID"]), str(row.get("FName", ""))))
    return result


def selected_campus(init_data: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[str, str]:
    user = init_data.get("userData", {})
    if not isinstance(user, Mapping):
        user = {}
    rows = school_rows(init_data)
    preferred = config.get("clock_in", {})
    preferred_id = preferred.get("campus") if isinstance(preferred, Mapping) else None
    if preferred_id in (None, "", "XXXXX"):
        preferred_id = user.get("FDefaultCampus")
    if preferred_id not in (None, "", "XXXXX"):
        preferred_id = str(preferred_id)
        for campus_id, name in rows:
            if campus_id == preferred_id:
                return campus_id, name
        return preferred_id, ""
    return rows[0] if rows else ("", "")


def location_values(config: Mapping[str, Any]) -> tuple[float, float, str]:
    location = config.get("location", {})
    if not isinstance(location, Mapping):
        raise ValueError("location 必须是 JSON 对象")
    latitude = float(real_value(location.get("latitude"), "location.latitude"))
    longitude = float(real_value(location.get("longitude"), "location.longitude"))
    address = str(location.get("address", ""))
    return latitude, longitude, address


def build_school_position(init_data: Mapping[str, Any]) -> dict[str, Any]:
    ranges: list[Any] = []
    rows = init_data.get("schoolData", [])
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            raw = row.get("FPosition")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, Mapping) and isinstance(parsed.get("range"), list):
                ranges.extend(parsed["range"])
    return {"range": ranges}


def build_check_payload(init_data: Mapping[str, Any], latitude: float, longitude: float) -> dict[str, Any]:
    return {
        "mapType": "amap",
        "longitude": longitude,
        "latitude": latitude,
        "range": json.dumps(build_school_position(init_data), ensure_ascii=False, separators=(",", ":")),
    }


def build_clock_in_payload(
    init_data: Mapping[str, Any],
    *,
    latitude: float,
    longitude: float,
    address: str,
    server_timestamp: int,
    ca_is_no: str = "0",
    matched_campus: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    params = init_data.get("paramsData", {})
    user = init_data.get("userData", {})
    if not isinstance(params, Mapping) or not isinstance(user, Mapping):
        raise ValueError("init.action 缺少 paramsData/userData")
    if matched_campus is not None:
        campus_value = matched_campus.get("id", matched_campus.get("ID", ""))
        campus = str(campus_value) if campus_value is not None else ""
        campus_name = str(
            matched_campus.get("title", matched_campus.get("name", matched_campus.get("FName", "")))
        )
    else:
        campus, campus_name = selected_campus(init_data, {})
    actual_location = " ".join(item for item in (campus_name, address) if item)
    return {
        "campus": campus,
        "lon": longitude,
        "lat": latitude,
        "startTime": params.get("FStartTime", ""),
        "endTime": params.get("FEndTime", ""),
        "actualLocation": actual_location,
        "caIsNo": ca_is_no or "0",
        "collUnit": user.get("FCollUnit", ""),
        "way": user.get("FWay", ""),
        "isLate": is_late(server_timestamp, params.get("FLateTime")),
    }


def aes_query_value(value: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    encryption = config.get("encryption", {})
    if not isinstance(encryption, Mapping):
        encryption = {}
    key_text = str(encryption.get("key") or H5_AES_KEY)
    iv_text = str(encryption.get("iv") or key_text)
    if key_text in PLACEHOLDERS:
        key_text = H5_AES_KEY
    if iv_text in PLACEHOLDERS:
        iv_text = key_text
    key = key_text.encode("utf-8")
    iv = iv_text.encode("utf-8")
    if len(key) != 16 or len(iv) != 16:
        raise ValueError("AES key/iv 必须是 16 字节")
    plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    base64_value = base64.b64encode(ciphertext).decode("ascii")
    return quote(base64_value, safe="-_.!~*'()")


def status_success(init_data: Mapping[str, Any]) -> bool:
    status = init_data.get("statusData")
    return isinstance(status, Mapping) and status.get("status") in {"SUCCESS", "PROCESSING"}


def response_shape(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "nested"
    if isinstance(value, Mapping):
        return {str(key): response_shape(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return {"type": "array", "items": [response_shape(item, depth + 1) for item in value[:2]]}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def print_preview(config: Mapping[str, Any], init_data: Mapping[str, Any], timestamp: int) -> None:
    latitude, longitude, address = location_values(config)
    clock_payload = build_clock_in_payload(
        init_data,
        latitude=latitude,
        longitude=longitude,
        address=address,
        server_timestamp=timestamp,
        ca_is_no=str(config.get("clock_in", {}).get("caIsNo", "0")) if isinstance(config.get("clock_in"), Mapping) else "0",
    )
    check_payload = build_check_payload(init_data, latitude, longitude)
    params = init_data.get("paramsData", {})
    status = init_data.get("statusData")
    print("协议预览（未调用 check.action/clockIn.action）:")
    print(f"  clockIn URL: {api_url(config, 'clockIn.action')}?param=<encrypted>")
    print("  method: GET")
    print("  headers: token, User-Agent")
    print(f"  check fields: {', '.join(check_payload)}")
    print(f"  clockIn fields: {', '.join(clock_payload)}")
    print(f"  init response shape: {response_shape(init_data)}")
    print(f"  server timestamp type: {type(timestamp).__name__}")
    print(f"  current status: {'already-signed' if status_success(init_data) else 'not-success'}")
    if isinstance(params, Mapping):
        print(f"  time window: {params.get('FStartTime', '<missing>')} - {params.get('FEndTime', '<missing>')}")
    print("  encrypted check query: <redacted>")
    print("  encrypted clockIn query: <redacted>")
    _ = status


def run(config: Mapping[str, Any], send: bool, auto_yes: bool = False) -> int:
    init_data = fetch_init(config)
    timestamp = fetch_server_timestamp(config)
    if not send:
        print_preview(config, init_data, timestamp)
        print("\nDRY-RUN：未发送 check.action 或 clockIn.action。")
        return 0

    request_config = config.get("request", {})
    if not isinstance(request_config, Mapping) or request_config.get("enabled") is not True:
        raise ValueError("request.enabled 必须明确设置为 true")
    if status_success(init_data):
        print("服务端已显示签到成功，停止，不重复提交。")
        return 0
    params = init_data.get("paramsData", {})
    if not isinstance(params, Mapping) or not in_time_window(timestamp, params.get("FStartTime"), params.get("FEndTime")):
        raise ValueError("当前不在服务端返回的签到时间窗口内，停止发送")
    latitude, longitude, address = location_values(config)
    check_payload = build_check_payload(init_data, latitude, longitude)
    check_query = aes_query_value(check_payload, config)
    check_data = unwrap_success(
        request_json(config, "check.action", "GET", query={"param": check_query}), "check.action"
    )
    if not isinstance(check_data, list) or not check_data:
        raise ValueError("check.action 未返回匹配校区，停止发送")
    matched = check_data[0] if isinstance(check_data[0], Mapping) else None
    clock_payload = build_clock_in_payload(
        init_data,
        latitude=latitude,
        longitude=longitude,
        address=address,
        server_timestamp=timestamp,
        ca_is_no=str(config.get("clock_in", {}).get("caIsNo", "0")) if isinstance(config.get("clock_in"), Mapping) else "0",
        matched_campus=matched,
    )
    matched_name = str(matched.get("title") or matched.get("name") or matched.get("FName") or "") if matched else ""
    print(f"即将向 {api_url(config, 'clockIn.action')} 发送一次真实签到请求。")
    print(f"定位命中校区：{matched_name or '（未识别）'}；提交字段：{', '.join(clock_payload)}")
    if auto_yes:
        print("已授权 --yes，跳过二次确认（request.enabled=true + --send + --yes 三重开关）。")
    elif input(f"输入 {CONFIRM_WORD} 才继续：").strip() != CONFIRM_WORD:
        print("未输入确认词，已取消。")
        return 2
    query = aes_query_value(clock_payload, config)
    result = unwrap_success(
        request_json(config, "clockIn.action", "GET", query={"param": query}), "clockIn.action"
    )
    print(f"clockIn.action 返回结构：{response_shape(result)}")
    print("已完成一次请求；请在 App 页面核对服务端状态。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="晚点名签到协议预览/授权测试运行器")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--send", action="store_true", help="执行范围校验并在确认后发送一次签到")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="在 request.enabled=true 且校验通过时跳过二次确认直接发送（仅在你明确授权时使用）",
    )
    args = parser.parse_args(argv)
    try:
        return run(load_config(args.config), send=args.send, auto_yes=args.yes)
    except (ValueError, TypeError, KeyError) as exc:
        print(f"配置/协议错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
