"""Search extracted APK files for exact high-value strings with byte offsets."""

from __future__ import annotations

import sys
from pathlib import Path

from inspect_hits import ascii_runs_with_offsets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


DEFAULT_NEEDLES = (
    "晚点名签到",
    "晚点",
    "签到",
    "点名",
    "signIn",
    "trackSignIn",
    "getSigned",
    "attendance",
    "checkIn",
    "service",
    "scheme",
    "http",
    "https",
    "quing",
    "fzu",
)


def print_raw_hits(data: bytes, needle: str) -> None:
    for encoding in ("utf-8", "utf-16le"):
        encoded = needle.encode(encoding)
        start = 0
        while True:
            offset = data.find(encoded, start)
            if offset < 0:
                break
            context_start = max(0, offset - 80)
            context_end = min(len(data), offset + len(encoded) + 160)
            context = data[context_start:context_end].decode("utf-8", "backslashreplace")
            print(f"RAW {encoding} 0x{offset:08x} {needle!r} {ascii(context)}")
            start = offset + max(1, len(encoded))


def scan(path: Path, needles: tuple[str, ...]) -> None:
    data = path.read_bytes()
    print(f"\n===== {path} ({len(data)} bytes) =====")
    seen: set[tuple[int, str]] = set()
    for offset, value in ascii_runs_with_offsets(data):
        folded = value.casefold()
        if len(value) <= 800 and any(needle.casefold() in folded for needle in needles):
            key = (offset, value)
            if key not in seen:
                print(f"ASCII 0x{offset:08x} {value[:800]!r}")
                seen.add(key)
    for needle in needles:
        print_raw_hits(data, needle)


arguments = sys.argv[1:]
if "--" in arguments:
    separator = arguments.index("--")
    file_arguments = arguments[:separator]
    needles = tuple(arguments[separator + 1 :]) or DEFAULT_NEEDLES
else:
    file_arguments = arguments
    needles = DEFAULT_NEEDLES

for argument in file_arguments:
    scan(Path(argument), needles)
