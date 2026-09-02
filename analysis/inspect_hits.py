"""Inspect high-confidence strings and their offsets in extracted APK binaries."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def ascii_runs_with_offsets(data: bytes, minimum: int = 4) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    start = None
    for index, byte in enumerate(data):
        if 32 <= byte <= 126:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                result.append((start, data[start:index].decode("ascii", "ignore")))
            start = None
    if start is not None and len(data) - start >= minimum:
        result.append((start, data[start:].decode("ascii", "ignore")))
    return result


PATH_RE = re.compile(r"^/[A-Za-z0-9._~:/?&=%+\-]+$")
URL_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?&=%+\-]+$")


def high_confidence_path(value: str) -> bool:
    if not (PATH_RE.fullmatch(value) or URL_RE.fullmatch(value)):
        return False
    if len(value) < 7 or len(value) > 500:
        return False
    if value.startswith("http"):
        return True
    lower = value.casefold()
    return (
        "/app/" in value
        or "/v1" in value
        or value.count("/") >= 3
        or any(
            marker in lower
            for marker in (
                "login",
                "logout",
                "signin",
                "sign-in",
                "checkin",
                "attendance",
                "service",
                "point",
                "location",
                "device",
                "token",
            )
        )
    )


def emit(path: Path) -> None:
    data = path.read_bytes()
    runs = ascii_runs_with_offsets(data)
    seen_paths: set[str] = set()
    paths: list[tuple[int, str]] = []
    hits: list[tuple[int, str]] = []
    exact_fields = {
        "latitude",
        "longitude",
        "deviceId",
        "deviceToken",
        "userId",
        "orgId",
        "serviceId",
        "serviceIds",
        "loginToken",
        "accountToken",
        "appToken",
        "timestamp",
        "timeStamp",
        "requestStartTimestamp",
        "requestEndTimestamp",
        "responseStartTimestamp",
        "responseEndTimestamp",
        "signIn",
        "trackSignIn",
        "getSigned",
    }
    keywords = (
        "signIn",
        "trackSignIn",
        "getSigned",
        "checkIn",
        "attendance",
        "签到",
        "晚点",
        "点名",
        "班级",
    )
    for offset, value in runs:
        if high_confidence_path(value) and value not in seen_paths:
            paths.append((offset, value))
            seen_paths.add(value)
        if value in exact_fields or any(keyword.casefold() in value.casefold() for keyword in keywords):
            hits.append((offset, value))
    print(f"\n===== {path} ({len(data)} bytes) =====")
    print(f"## HIGH-CONFIDENCE PATHS ({len(paths)})")
    for offset, value in paths:
        print(f"0x{offset:08x}\t{value}")
    print(f"## CHECK-IN/FIELD HITS ({len(hits)})")
    for offset, value in hits:
        print(f"0x{offset:08x}\t{value[:1000]}")


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        emit(Path(argument))
