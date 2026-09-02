"""Print application-related values from the resources.arsc global pool."""

from __future__ import annotations

import sys
from pathlib import Path

from parse_arsc import string_pool, u16

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


for argument in sys.argv[1:]:
    path = Path(argument)
    data = path.read_bytes()
    if u16(data, 0) != 0x0002:
        continue
    pool, _ = string_pool(data, u16(data, 2))
    print(f"=== {path} global_strings={len(pool)} ===")
    markers = ("APP", "URL", "HOST", "API", "FZ", "FDXY", "QUING", "SCHEME", "ENV", "RELEASE", "HTTP")
    for index, value in enumerate(pool):
        folded = value.casefold()
        if any(marker.casefold() in folded for marker in markers):
            print(f"{index:04d}\t{value}")
