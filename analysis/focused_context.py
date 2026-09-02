"""Print concise string-table neighborhoods for auth/service request classes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from inspect_hits import ascii_runs_with_offsets, high_confidence_path


TARGETS = (
    "KYAppAccountLoginRequest",
    "KYBizAccountLoginRequest",
    "KYAppAccountLoginViewModel",
    "KYBizAccountLoginViewModel",
    "_accountAndPassword",
    "username",
    "password",
    "loginType",
    "authCode",
    "accountId",
    "sid",
    "loginHostPath",
    "confirmLoginPath",
    "_loginRequest",
    "KYAppVendorServiceCategoryDetailRequest",
    "KYAppVendorServiceMineListRequest",
    "KYAppVendorServiceInfoRequest",
    "KYOrgVendorServiceRequest",
    "KYVendorServiceOperatorRequest",
    "getAppServiceInfoPath",
    "getServiceListByGroupId",
    "getServiceListByType",
    "getMyServiceList",
    "getAppUrlById",
    "getAppIdUrl",
    "getPageService",
    "getMyHomeServiceList",
)

FIELD_RE = re.compile(
    r"^(?:get|set|init):(?:_)?(?:account|login|password|username|phone|code|auth|sid|token|user|org|group|service|url|scheme|page|app|device|location|latitude|longitude|time)"
)
REQUEST_RE = re.compile(r"(?:KY|IKY)[A-Za-z0-9_]*(?:Request|Response|Bean|ViewModel|Page|Processor)$")


def useful(value: str) -> bool:
    return (
        high_confidence_path(value)
        or value.startswith(("package:ky_app_account", "package:ky_biz_account", "package:ky_app_vendor_service", "package:ky_biz_vendor_service"))
        or FIELD_RE.match(value) is not None
        or REQUEST_RE.search(value.strip('"')) is not None
        or value in {"username", "password", "loginType", "authCode", "accountId", "sid", "serviceId", "serviceName", "serviceUrl", "urlType", "pageType", "scheme", "appId", "orgId", "userId", "deviceId", "latitude", "longitude", "timestamp", "appToken", "loginToken", "accountToken"}
    )


for argument in sys.argv[1:]:
    path = Path(argument)
    runs = ascii_runs_with_offsets(path.read_bytes())
    print(f"=== {path} ===")
    seen: set[tuple[str, int]] = set()
    for target in TARGETS:
        for offset, value in runs:
            if target.casefold() not in value.casefold():
                continue
            print(f"\nTARGET {target!r} AT 0x{offset:08x}")
            start = max(0, offset - 2500)
            end = offset + 2500
            for nearby_offset, nearby_value in runs:
                if start <= nearby_offset <= end and useful(nearby_value) and len(nearby_value) <= 500:
                    key = (nearby_value, nearby_offset)
                    if key not in seen:
                        print(f"0x{nearby_offset:08x}\t{nearby_value}")
                        seen.add(key)
