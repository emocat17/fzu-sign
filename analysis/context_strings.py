"""Show nearby AOT string literals around selected high-value hits."""

from __future__ import annotations

import sys
from pathlib import Path

from inspect_hits import ascii_runs_with_offsets, high_confidence_path


TARGETS = (
    "trackSignIn",
    "signIn",
    "getSigned",
    "latitude",
    "longitude",
    "deviceId",
    "serviceId",
    "userId",
    "orgId",
    "loginToken",
    "appToken",
    "package:ky_app_vendor_service",
    "package:ky_app_account",
    "getAppServiceInfoPath",
    "getServiceListByGroupId",
    "getServiceListByType",
    "getMyServiceList",
    "getAppUrlById",
    "getAppIdUrl",
    "getMyHomeServiceList",
    "getPageService",
    "saveBatchMyService",
    "KYAppVendorServiceCategoryDetailRequest",
    "KYAppVendorServiceMineListRequest",
    "KYAppVendorServiceInfoRequest",
    "KYOrgVendorServiceRequest",
    "KYVendorServiceOperatorRequest",
)


def useful(value: str) -> bool:
    folded = value.casefold()
    if len(value) > 500:
        return False
    return (
        high_confidence_path(value)
        or "package:" in value
        or any(target.casefold() in folded for target in TARGETS)
        or value.startswith(("get:", "set:", "init:"))
        or any(marker in folded for marker in ("request", "response", "json", "http", "token", "location", "service", "scheme"))
    )


def scan(path: Path) -> None:
    data = path.read_bytes()
    runs = ascii_runs_with_offsets(data)
    for target in TARGETS:
        for index, (offset, value) in enumerate(runs):
            if target.casefold() not in value.casefold():
                continue
            print(f"\n=== {path} TARGET {target!r} AT 0x{offset:08x} ===")
            start = max(0, offset - 4096)
            end = offset + 4096
            for nearby_offset, nearby_value in runs:
                if start <= nearby_offset <= end and len(nearby_value) <= 500 and useful(nearby_value):
                    print(f"0x{nearby_offset:08x}\t{nearby_value}")


for argument in sys.argv[1:]:
    scan(Path(argument))
