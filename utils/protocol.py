"""Read-only protocol fetches and response introspection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from utils.net import request_json, unwrap_success


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
