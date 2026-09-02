"""Small reader for Android resources.arsc string/value entries."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def string_pool(data: bytes, start: int) -> tuple[list[str], int]:
    count = u32(data, start + 8)
    flags = u32(data, start + 16)
    strings_offset = u32(data, start + 20)
    offsets = start + 28
    text_start = start + strings_offset
    utf8 = bool(flags & 0x100)
    result: list[str] = []
    for index in range(count):
        cursor = text_start + u32(data, offsets + index * 4)
        if utf8:
            first = data[cursor]
            cursor += 1 + (1 if first & 0x80 else 0)
            length = data[cursor]
            cursor += 1
            if length & 0x80:
                length = ((length & 0x7F) << 8) | data[cursor]
                cursor += 1
            result.append(data[cursor : cursor + length].decode("utf-8", "replace"))
        else:
            length = u16(data, cursor)
            cursor += 2
            if length & 0x8000:
                length = ((length & 0x7FFF) << 16) | u16(data, cursor)
                cursor += 2
            result.append(data[cursor : cursor + length * 2].decode("utf-16le", "replace"))
    return result, u32(data, start + 4)


def get(values: list[str], index: int) -> str:
    return values[index] if 0 <= index < len(values) else f"@index[{index}]"


def typed_value(global_strings: list[str], value_type: int, value_data: int) -> str:
    if value_type == 0x03:
        return get(global_strings, value_data)
    if value_type == 0x12:
        return "true" if value_data else "false"
    if value_type == 0x01:
        return f"@0x{value_data:08x}"
    if value_type == 0x10:
        return str(value_data)
    return f"<type=0x{value_type:02x},data=0x{value_data:08x}>"


def parse_package(data: bytes, package_start: int, package_size: int, global_strings: list[str]) -> list[str]:
    package_id = u32(data, package_start + 8)
    type_offset = u32(data, package_start + 284) if u16(data, package_start + 2) >= 288 else 0
    type_strings_start = package_start + u32(data, package_start + 268)
    key_strings_start = package_start + u32(data, package_start + 276)
    type_strings, _ = string_pool(data, type_strings_start)
    key_strings, _ = string_pool(data, key_strings_start)
    interesting: list[str] = []
    resource_values: dict[int, tuple[str, str]] = {}
    cursor = package_start + u16(data, package_start + 2)
    package_end = package_start + package_size
    while cursor + 8 <= package_end:
        chunk_type = u16(data, cursor)
        header_size = u16(data, cursor + 2)
        chunk_size = u32(data, cursor + 4)
        if chunk_size < 8 or cursor + chunk_size > package_end:
            break
        if chunk_type == 0x0201 and header_size >= 20:
            type_id = u8(data, cursor + 8)
            entry_count = u32(data, cursor + 16)
            entries_start = u32(data, cursor + 20)
            offsets_end = header_size + entry_count * 4
            if offsets_end > chunk_size or entries_start >= chunk_size:
                cursor += chunk_size
                continue
            type_name = get(type_strings, type_id - 1)
            offsets_start = cursor + header_size
            for entry_index in range(entry_count):
                offset = u32(data, offsets_start + entry_index * 4)
                if offset == 0xFFFFFFFF:
                    continue
                entry = cursor + entries_start + offset
                if entry + 8 > cursor + chunk_size:
                    continue
                flags = u16(data, entry + 2)
                key_name = get(key_strings, u32(data, entry + 4))
                resource_id = (package_id << 24) | ((type_id + type_offset) << 16) | entry_index
                if flags & 0x0001:
                    value_text = "<complex>"
                elif entry + 16 <= cursor + chunk_size:
                    value_type = data[entry + 11]
                    value_data = u32(data, entry + 12)
                    value_text = typed_value(global_strings, value_type, value_data)
                else:
                    value_text = "<invalid>"
                resource_values[resource_id] = (f"{type_name}/{key_name}", value_text)
        cursor += chunk_size
    markers = ("scheme", "network", "security", "url", "label", "app", "host", "base", "fdxy", "fzu", "quing")
    for resource_id, (name, resource_value) in sorted(resource_values.items()):
        folded = f"{name} {resource_value}".casefold()
        if resource_id in (0x7F0E0009, 0x7F0E000B, 0x7F110005) or any(marker in folded for marker in markers):
            interesting.append(f"0x{resource_id:08x}\t{name}\t{resource_value}")
    return interesting


def u8(data: bytes, offset: int) -> int:
    return data[offset]


def parse(path: Path) -> None:
    data = path.read_bytes()
    print(f"=== {path} ({len(data)} bytes) ===")
    if u16(data, 0) != 0x0002:
        print("not a resource table")
        return
    table_header = u16(data, 2)
    cursor = table_header
    global_strings: list[str] = []
    if u16(data, cursor) == 0x0001:
        global_strings, pool_size = string_pool(data, cursor)
        print(f"GLOBAL_STRING_POOL {len(global_strings)} strings")
        cursor += pool_size
    package_count = u32(data, 8)
    packages = 0
    while cursor + 8 <= len(data) and packages < package_count:
        chunk_type = u16(data, cursor)
        chunk_size = u32(data, cursor + 4)
        if chunk_size < 8 or cursor + chunk_size > len(data):
            break
        if chunk_type == 0x0200:
            packages += 1
            print(f"PACKAGE {packages} size={chunk_size}")
            for line in parse_package(data, cursor, chunk_size, global_strings):
                print(line)
        cursor += chunk_size


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        parse(Path(argument))
