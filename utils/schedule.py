"""Sign-in time-window and late-flag calculations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from utils.config import real_value


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
