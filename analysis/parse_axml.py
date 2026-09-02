"""Minimal dependency-free Android binary XML (AXML) reader."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_string_pool(data: bytes, chunk_start: int) -> tuple[list[str], int]:
    string_count = u32(data, chunk_start + 8)
    flags = u32(data, chunk_start + 16)
    strings_offset = u32(data, chunk_start + 20)
    offsets_start = chunk_start + 28
    strings_start = chunk_start + strings_offset
    utf8 = bool(flags & 0x100)
    strings: list[str] = []
    for index in range(string_count):
        cursor = strings_start + u32(data, offsets_start + index * 4)
        if utf8:
            first = data[cursor]
            cursor += 1
            if first & 0x80:
                cursor += 1
            byte_length = data[cursor]
            cursor += 1
            if byte_length & 0x80:
                byte_length = ((byte_length & 0x7F) << 8) | data[cursor]
                cursor += 1
            strings.append(data[cursor : cursor + byte_length].decode("utf-8", "replace"))
        else:
            char_length = u16(data, cursor)
            cursor += 2
            if char_length & 0x8000:
                char_length = ((char_length & 0x7FFF) << 16) | u16(data, cursor)
                cursor += 2
            strings.append(data[cursor : cursor + char_length * 2].decode("utf-16le", "replace"))
    return strings, u32(data, chunk_start + 4)


def value(strings: list[str], index: int) -> str:
    return strings[index] if 0 <= index < len(strings) else f"@string[{index}]"


def typed_value(strings: list[str], value_type: int, value_data: int) -> str:
    if value_type == 0x03:
        return value(strings, value_data)
    if value_type == 0x12:
        return "true" if value_data else "false"
    if value_type == 0x10:
        return str(value_data)
    if value_type == 0x11:
        return f"0x{value_data:x}"
    if value_type == 0x01:
        return f"@0x{value_data:08x}"
    return f"<type=0x{value_type:02x},data=0x{value_data:08x}>"


def parse(path: Path) -> None:
    data = path.read_bytes()
    strings: list[str] = []
    cursor = 0
    print(f"=== {path} ({len(data)} bytes) ===")
    while cursor + 8 <= len(data):
        chunk_type = u16(data, cursor)
        header_size = u16(data, cursor + 2)
        chunk_size = u32(data, cursor + 4)
        if chunk_size < 8 or cursor + chunk_size > len(data):
            break
        if cursor == 0 and chunk_type == 0x0003:
            cursor += header_size
            continue
        if chunk_type == 0x0001:
            strings, _ = read_string_pool(data, cursor)
            print(f"STRING_POOL {len(strings)} strings")
        elif chunk_type == 0x0102 and strings:
            name_index = u32(data, cursor + 20)
            attr_start = u16(data, cursor + 24)
            attr_size = u16(data, cursor + 26)
            attr_count = u16(data, cursor + 28)
            attrs = []
            # attributeStart is relative to the ResXMLTree_attrExt structure,
            # which begins 16 bytes into the start-element node.
            attr_cursor = cursor + 16 + attr_start
            for index in range(attr_count):
                base = attr_cursor + index * attr_size
                attr_name = value(strings, u32(data, base + 4))
                raw_index = u32(data, base + 8)
                typed_size = u16(data, base + 12)
                value_type = data[base + 15]
                value_data = u32(data, base + 16)
                raw = value(strings, raw_index) if raw_index != 0xFFFFFFFF else ""
                rendered = raw or typed_value(strings, value_type, value_data)
                attrs.append(f"{attr_name}={rendered}")
            print(f"START {'  ' * 0}{value(strings, name_index)}")
            for attr in attrs:
                print(f"  {attr}")
        elif chunk_type == 0x0103 and strings:
            name_index = u32(data, cursor + 20)
            print(f"END {value(strings, name_index)}")
        cursor += chunk_size


for argument in sys.argv[1:]:
    parse(Path(argument))
