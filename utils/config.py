"""Configuration loading, validation, URL helpers and the arming switch."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = BASE_DIR / "data.json"

H5_AES_KEY = "apexinfoapexinfo"
H5_PATH_PREFIX = "/livecloud/project/fzu/attn/"
PLACEHOLDERS = {"", "XXXXX", "<redacted>", "<runtime>", "<actual>"}

SHARED_KEYS = ("app", "clock_in", "request", "encryption", "timeout_seconds", "retry_times", "WXKey")
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_RETRY_TIMES = 3


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


def timeout_seconds(config: Mapping[str, Any]) -> float:
    try:
        return float(config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return float(DEFAULT_TIMEOUT_SECONDS)


def retry_times(config: Mapping[str, Any]) -> int:
    try:
        value = int(config.get("retry_times", DEFAULT_RETRY_TIMES))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_TIMES
    return max(1, value)


def user_enabled(config: Mapping[str, Any]) -> bool:
    return config.get("enabled") is not False


def should_auto_send(config: Mapping[str, Any]) -> bool:
    """Master ``request.enabled`` plus per-user ``enabled`` (default true)."""
    request_config = config.get("request", {})
    master = isinstance(request_config, Mapping) and request_config.get("enabled") is True
    return master and user_enabled(config)


def summary_wx_key(config: Mapping[str, Any]) -> str:
    key = config.get("_summary_WXKey", config.get("WXKey"))
    return str(key).strip() if key else ""


def personal_wx_key(config: Mapping[str, Any]) -> str:
    key = config.get("WXKey")
    text = str(key).strip() if key else ""
    shared = summary_wx_key(config)
    if text and text != shared:
        return text
    return ""


def user_label(config: Mapping[str, Any]) -> str:
    name = config.get("name")
    text = str(name).strip() if name is not None else ""
    return text or "未命名"


def _merge_user(shared: Mapping[str, Any], user: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(shared)
    merged["_summary_WXKey"] = shared.get("WXKey", "")
    for key, value in user.items():
        if key == "name":
            continue
        merged[key] = value
    merged["name"] = user_label(user)
    merged.setdefault("enabled", True)
    return merged


def user_configs(config: Mapping[str, Any], name: str | None = None) -> list[dict[str, Any]]:
    """Expand a root config into per-user runtime configs.

    Shared fields (``app`` / ``encryption`` / ``request`` / ``WXKey`` / …) stay
    at the root. Each ``users[]`` entry supplies ``name``, ``auth`` and
    ``location``. Legacy single-user files without ``users`` still work.
    """
    users = config.get("users")
    if not isinstance(users, list):
        merged = dict(config)
        merged.setdefault("name", user_label(merged))
        merged.setdefault("enabled", True)
        merged.setdefault("_summary_WXKey", config.get("WXKey", ""))
        if name and merged["name"] != name:
            raise ValueError(f"未找到用户: {name}")
        return [merged]
    if not users:
        raise ValueError("users 数组为空")
    shared = {key: config[key] for key in SHARED_KEYS if key in config}
    selected: list[dict[str, Any]] = []
    for index, user in enumerate(users):
        if not isinstance(user, Mapping):
            raise ValueError(f"users[{index}] 必须是 JSON 对象")
        merged = _merge_user(shared, user)
        if name is None or merged["name"] == name:
            selected.append(merged)
    if name and not selected:
        raise ValueError(f"未找到用户: {name}")
    if not selected:
        raise ValueError("users 数组为空")
    return selected


def save_user_auth(path: Path, name: str, cookie: str, token: str = "") -> None:
    """Persist refreshed Cookie/token back into ``data.json`` without dropping other users."""
    root = load_config(path)
    users = root.get("users")
    if isinstance(users, list):
        matched = False
        for user in users:
            if isinstance(user, dict) and user_label(user) == name:
                auth = user.setdefault("auth", {})
                if not isinstance(auth, dict):
                    raise ValueError(f"{name} 的 auth 必须是 JSON 对象")
                if cookie:
                    auth["cookie"] = cookie
                if token:
                    auth["token"] = token
                matched = True
                break
        if not matched:
            raise ValueError(f"未找到用户: {name}")
    else:
        auth = root.setdefault("auth", {})
        if not isinstance(auth, dict):
            raise ValueError("auth 必须是 JSON 对象")
        if name and user_label(root) not in {name, "未命名"}:
            raise ValueError(f"未找到用户: {name}")
        if cookie:
            auth["cookie"] = cookie
        if token:
            auth["token"] = token
    path.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_user_cookie(path: Path, name: str, cookie: str) -> None:
    save_user_auth(path, name, cookie)


def validate_user_config(config: Mapping[str, Any]) -> None:
    label = user_label(config)
    auth = config.get("auth", {})
    if not isinstance(auth, Mapping):
        raise ValueError(f"{label}: auth 必须是 JSON 对象")
    token = str(auth.get("token") or "").strip()
    cookie = str(auth.get("cookie") or "").strip()
    username = str(auth.get("username") or "").strip()
    password = str(auth.get("password") or "").strip()
    has_token = token not in PLACEHOLDERS
    has_cookie = cookie not in PLACEHOLDERS
    has_login = username not in PLACEHOLDERS and password not in PLACEHOLDERS
    if not has_token and not has_cookie and not has_login:
        raise ValueError(f"请填写 {label}.auth.token，或填写 Cookie / 账号密码以便自动获取")
    location = config.get("location", {})
    if not isinstance(location, Mapping):
        raise ValueError(f"{label}: location 必须是 JSON 对象")
    real_value(location.get("latitude"), f"{label}.location.latitude")
    real_value(location.get("longitude"), f"{label}.location.longitude")
    real_value(location.get("address"), f"{label}.location.address")
    try:
        float(location.get("latitude"))
        float(location.get("longitude"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: location.latitude / longitude 必须是数字") from exc
