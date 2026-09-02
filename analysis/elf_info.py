"""Print ELF64 sections and dynamic symbols for native Flutter libraries."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def cstring(data: bytes, offset: int) -> str:
    end = data.find(b"\x00", offset)
    return data[offset:end].decode("utf-8", "replace")


def inspect(path: Path) -> None:
    data = path.read_bytes()
    print(f"=== {path} ({len(data)} bytes) ===")
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        print("not ELF64 little-endian")
        return
    machine = u16(data, 18)
    phoff = u64(data, 32)
    shoff = u64(data, 40)
    phentsize = u16(data, 54)
    phnum = u16(data, 56)
    shentsize = u16(data, 58)
    shnum = u16(data, 60)
    shstrndx = u16(data, 62)
    print(f"machine=0x{machine:x} phnum={phnum} shnum={shnum}")
    sections = []
    for index in range(shnum):
        start = shoff + index * shentsize
        sections.append(
            {
                "index": index,
                "name": u32(data, start),
                "type": u32(data, start + 4),
                "offset": u64(data, start + 24),
                "size": u64(data, start + 32),
                "link": u32(data, start + 40),
                "entsize": u64(data, start + 56),
            }
        )
    shstr = sections[shstrndx]
    shstr_data = data[shstr["offset"] : shstr["offset"] + shstr["size"]]
    for section in sections:
        section["name_text"] = cstring(shstr_data, section["name"])
    for section in sections:
        if section["name_text"] in (".text", ".rodata", ".dynstr", ".dynsym", ".symtab", ".strtab", ".debug_info"):
            print(f"SECTION {section['index']} {section['name_text']} off=0x{section['offset']:x} size=0x{section['size']:x} entsize=0x{section['entsize']:x}")
    dynstr = next((s for s in sections if s["name_text"] == ".dynstr"), None)
    dynsym = next((s for s in sections if s["name_text"] == ".dynsym"), None)
    if dynstr and dynsym and dynsym["entsize"]:
        strings = data[dynstr["offset"] : dynstr["offset"] + dynstr["size"]]
        print("DYNAMIC_SYMBOLS")
        for offset in range(dynsym["offset"], dynsym["offset"] + dynsym["size"], dynsym["entsize"]):
            name_index = u32(data, offset)
            value = u64(data, offset + 8)
            size = u64(data, offset + 16)
            name = cstring(strings, name_index)
            if name:
                print(f"0x{value:x}\t{size}\t{name}")


for argument in sys.argv[1:]:
    inspect(Path(argument))
