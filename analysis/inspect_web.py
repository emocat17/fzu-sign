"""Fetch public H5 chunks and print route/request clues without executing JS."""

from __future__ import annotations

import re
import sys
from urllib.request import Request, urlopen

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


BASE = "https://app.fzu.edu.cn/fd-app/"
FILES = (
    "js/m.c820b729.js",
    "js/chunk-0755c7c4.d870d35e.js",
    "js/chunk-1774564e.c3d086d8.js",
    "js/chunk-522d12fb.83e0009d.js",
    "js/chunk-5986acc2.8faa2511.js",
    "js/chunk-c6672734.dd621589.js",
)
TERMS = (
    "getRequest",
    "postRequest",
    "postRequestUrl",
    "serviceId",
    "appId",
    "userId",
    "token",
    "Authorization",
    "sign",
    "签到",
    "点名",
    "attendance",
    "location",
)
ROUTE_RE = re.compile(r"['\"](/[A-Za-z0-9_./?=&:%+\-]{3,})['\"]")
URL_RE = re.compile(r"https?://[^\"'`\\\s]{4,}")


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def contexts(content: str, term: str) -> list[str]:
    result: list[str] = []
    for match in re.finditer(re.escape(term), content, re.IGNORECASE):
        start = max(0, match.start() - 220)
        end = min(len(content), match.end() + 380)
        result.append(re.sub(r"\s+", " ", content[start:end]))
        if len(result) >= 8:
            break
    return result


for filename in FILES:
    url = BASE + filename
    try:
        content = fetch(url)
    except Exception as exc:
        print(f"=== {filename} ERROR {exc} ===")
        continue
    print(f"\n=== {filename} length={len(content)} ===")
    routes = sorted(set(ROUTE_RE.findall(content)))
    urls = sorted(set(URL_RE.findall(content)))
    print("ROUTES")
    for route in routes:
        print(route)
    print("URLS")
    for external_url in urls:
        print(external_url[:500])
    for term in TERMS:
        hits = contexts(content, term)
        if hits:
            print(f"TERM {term} COUNT={len(list(re.finditer(re.escape(term), content, re.IGNORECASE)))}")
            for hit in hits:
                print(ascii(hit[:900]))
