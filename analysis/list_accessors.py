"""List exact Dart getter/setter names likely related to auth or services."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from inspect_hits import ascii_runs_with_offsets


MARKERS = (
    "login",
    "logout",
    "password",
    "passwd",
    "phone",
    "code",
    "auth",
    "account",
    "sid",
    "token",
    "user",
    "org",
    "device",
    "service",
    "group",
    "page",
    "url",
    "scheme",
    "location",
    "latitude",
    "longitude",
    "time",
    "sign",
    "check",
)


for argument in sys.argv[1:]:
    path = Path(argument)
    data = path.read_bytes()
    values: set[str] = set()
    for _, text in ascii_runs_with_offsets(data):
        for item in re.findall(r"(?:get|set|init):[A-Za-z_][A-Za-z0-9_]*", text):
            if any(marker in item.casefold() for marker in MARKERS):
                values.add(item)
    print(f"=== {path} ({len(values)} accessors) ===")
    for item in sorted(values):
        print(item)
