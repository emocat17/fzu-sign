"""Small dependency-free printable-string scanner for APK reverse engineering."""

from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


NEEDLES = (
    "http://",
    "https://",
    "ws://",
    "wss://",
    "api",
    "sign",
    "check",
    "attendance",
    "service",
    "login",
    "token",
    "auth",
    "location",
    "latitude",
    "longitude",
    "device",
    "晚点",
    "签到",
    "点名",
    "服务",
    "学生",
    "班级",
    "校验",
    "打卡",
)


def is_hit(value: str) -> bool:
    folded = value.casefold()
    return any(needle.casefold() in folded for needle in NEEDLES)


def ascii_runs(data: bytes, minimum: int = 4) -> list[str]:
    result: list[str] = []
    current = bytearray()
    for byte in data:
        if 32 <= byte <= 126:
            current.append(byte)
        else:
            if len(current) >= minimum:
                result.append(current.decode("ascii", "ignore"))
            current.clear()
    if len(current) >= minimum:
        result.append(current.decode("ascii", "ignore"))
    return result


def text_chunks(text: str, minimum: int = 2) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    for char in text:
        codepoint = ord(char)
        if codepoint >= 32 and not 127 <= codepoint <= 159:
            current.append(char)
        else:
            if len(current) >= minimum:
                result.append("".join(current))
            current.clear()
    if len(current) >= minimum:
        result.append("".join(current))
    return result


def utf16le_runs(data: bytes, minimum_chars: int = 3) -> list[str]:
    result: list[str] = []
    current = bytearray()
    index = 0
    while index + 1 < len(data):
        if 32 <= data[index] <= 126 and data[index + 1] == 0:
            current.extend(data[index : index + 2])
            index += 2
        else:
            if len(current) >= minimum_chars * 2:
                result.append(current.decode("utf-16le", "ignore"))
            current.clear()
            index += 1
    if len(current) >= minimum_chars * 2:
        result.append(current.decode("utf-16le", "ignore"))
    return result


def scan(path: str) -> None:
    data = open(path, "rb").read()
    print(f"=== {path} ({len(data)} bytes) ===")
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    decoded = data.decode("utf-8", "ignore")
    for kind, values in (
        ("ASCII", ascii_runs(data)),
        ("UTF8", text_chunks(decoded)),
        ("UTF16", utf16le_runs(data)),
    ):
        for value in values:
            if is_hit(value):
                value = value[:800]
                if value not in seen:
                    found.append((kind, value))
                    seen.add(value)
    for kind, value in found[:700]:
        print(kind, repr(value))
    print("MATCHES", len(found))


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        scan(argument)
