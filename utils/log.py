"""Append-only daily log files under ``logs/``."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from utils.config import BASE_DIR
from utils.user_info import get_current_time

LOG_DIR = BASE_DIR / "logs"


def log_path() -> Path:
    return LOG_DIR / f"zhfd-{datetime.now().strftime('%Y%m%d')}.log"


def write_log(message: str, *, error: bool = False) -> None:
    line = f"{get_current_time()} {message}"
    stream = sys.stderr if error else sys.stdout
    print(message, file=stream)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        print(f"[日志] 写入失败，已跳过：{exc}", file=sys.stderr)
