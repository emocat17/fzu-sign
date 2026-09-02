"""Read exact strings and class/method references from a DEX without jadx."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def uleb128(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7


def strings(data: bytes) -> list[str]:
    count = u32(data, 0x38)
    offset = u32(data, 0x3C)
    result: list[str] = []
    for index in range(count):
        item_offset = u32(data, offset + index * 4)
        _, cursor = uleb128(data, item_offset)
        end = data.find(b"\x00", cursor)
        result.append(data[cursor:end].decode("utf-8", "replace"))
    return result


def main(path: Path) -> None:
    data = path.read_bytes()
    if not data.startswith(b"dex\n"):
        print("not a DEX file")
        return
    values = strings(data)
    needles = (
        "http",
        "https",
        "fzu",
        "fdxy",
        "quing",
        "login",
        "token",
        "service",
        "sign",
        "check",
        "location",
        "permission",
        "flutter",
        "native",
    )
    print(f"=== {path} ({len(data)} bytes) strings={len(values)} ===")
    for index, value in enumerate(values):
        folded = value.casefold()
        if any(needle in folded for needle in needles):
            print(f"{index:06d}\t{value}")


for argument in sys.argv[1:]:
    main(Path(argument))
