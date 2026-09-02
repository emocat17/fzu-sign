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

SHARED_KEYS = ("app", "clock_in", "request", "encryption", "timeout_seconds", "WXKey")


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


def should_auto_send(config: Mapping[str, Any]) -> bool:
    """The single arming switch: ``python main.py`` signs in iff enabled=true."""
    request_config = config.get("request", {})
    return isinstance(request_config, Mapping) and request_config.get("enabled") is True


def user_label(config: Mapping[str, Any]) -> str:
    name = config.get("name")
    text = str(name).strip() if name is not None else ""
    return text or "未命名"


def _merge_user(shared: Mapping[str, Any], user: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(shared)
    for key, value in user.items():
        if key == "name":
            continue
        merged[key] = value
    merged["name"] = user_label(user)
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
