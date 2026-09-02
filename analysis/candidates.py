"""Print low-noise endpoint and check-in related strings from extracted binaries."""

from __future__ import annotations

import sys
from pathlib import Path
import re

from extract_strings import ascii_runs, text_chunks, utf16le_runs


def collect(data: bytes) -> list[str]:
    values = ascii_runs(data) + text_chunks(data.decode("utf-8", "ignore")) + utf16le_runs(data)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value.strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def print_group(title: str, values: list[str]) -> None:
    print(f"\n## {title} ({len(values)})")
    for value in values:
        print(value[:1000])


def is_ascii_text(value: str) -> bool:
    return all(32 <= ord(char) <= 126 for char in value)


PATH_RE = re.compile(r"^/[A-Za-z0-9._~:/?&=%+\-]+$")
URL_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?&=%+\-]+$")


for argument in sys.argv[1:]:
    path = Path(argument)
    values = collect(path.read_bytes())
    lower = [(value, value.casefold()) for value in values]
    endpoints = [
        value
        for value, folded in lower
        if (PATH_RE.fullmatch(value) or URL_RE.fullmatch(value))
        and len(value) <= 500
    ]
    endpoint_keywords = (
        "api",
        "auth",
        "login",
        "service",
        "sign",
        "check",
        "attendance",
        "clock",
        "point",
        "name",
        "late",
        "report",
        "location",
    )
    related = [
        value
        for value, folded in lower
        if any(keyword in folded for keyword in endpoint_keywords)
        and len(value) <= 500
        and is_ascii_text(value)
        and ("package:" in value or value.startswith(("_", "get:", "set:", "init:")) or "request" in folded or "json" in folded)
    ]
    fields = [
        value
        for value, folded in lower
        if any(keyword in folded for keyword in ("latitude", "longitude", "deviceid", "userid", "orgid", "serviceid", "token", "timestamp", "signin", "签到", "点名", "位置"))
        and len(value) <= 300
        and (is_ascii_text(value) or value in ("签到", "点名", "位置"))
    ]
    print(f"\n===== {path} ({path.stat().st_size} bytes) =====")
    print_group("ENDPOINT-LIKE", sorted(set(endpoints)))
    print_group("RELATED-SYMBOLS", sorted(set(related)))
    print_group("FIELD-OR-CHECKIN", sorted(set(fields)))
