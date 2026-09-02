"""Campus / location handling and check & clockIn payload builders."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from utils.config import real_value
from utils.schedule import is_late


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
