"""Inventory Flutter AOT symbol-like strings relevant to service loading."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from inspect_hits import ascii_runs_with_offsets, high_confidence_path


TOKEN_RE = re.compile(
    r"(?:KY|IKY)[A-Za-z0-9_]+(?:Request|Response|Bean|Page|Widget|ViewModel|Object|Processor|Config|Api|Service|Item|List|Mixin|Notifier)"
)


def scan(path: Path) -> None:
    data = path.read_bytes()
    runs = ascii_runs_with_offsets(data)
    packages: set[str] = set()
    symbols: set[str] = set()
    routes: set[str] = set()
    fields: set[str] = set()
    accessors: set[str] = set()
    field_names = (
        "groupId",
        "serviceId",
        "serviceIds",
        "serviceCode",
        "serviceName",
        "serviceUrl",
        "serviceType",
        "serviceData",
        "url",
        "scheme",
        "pageType",
        "appId",
        "orgId",
        "userId",
        "deviceId",
        "latitude",
        "longitude",
        "GPSLatitude",
        "GPSLongitude",
        "timestamp",
        "appToken",
        "loginToken",
        "accountToken",
        "accessToken",
        "Authorization",
        "Cookie",
    )
    for _, value in runs:
        if "package:ky_app_vendor_service" in value or "package:ky_biz_vendor_service" in value:
            packages.add(value)
        for symbol in TOKEN_RE.findall(value):
            folded = symbol.casefold()
            if any(marker in folded for marker in ("vendor", "service", "org", "account", "location", "auth")):
                symbols.add(symbol)
        if high_confidence_path(value):
            routes.add(value)
        for field in field_names:
            if value == field or field in value:
                fields.add(value[:300])
        for accessor in re.findall(r"(?:get|set):[A-Za-z_][A-Za-z0-9_]*", value):
            folded = accessor.casefold()
            if any(marker in folded for marker in ("service", "group", "page", "url", "scheme", "app", "org", "user", "device", "location", "token", "sign", "time")):
                accessors.add(accessor)
    print(f"\n===== {path} ({len(data)} bytes) =====")
    print("## SERVICE PACKAGES")
    for item in sorted(packages):
        print(item)
    print("## SERVICE-RELATED SYMBOLS")
    for item in sorted(symbols):
        print(item)
    print("## ROUTES")
    for item in sorted(routes):
        print(item)
    print("## FIELD CANDIDATES")
    for item in sorted(fields):
        print(item)
    print("## ACCESSOR CANDIDATES")
    for item in sorted(accessors):
        print(item)


for argument in sys.argv[1:]:
    scan(Path(argument))
