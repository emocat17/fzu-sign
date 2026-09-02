"""WeChat (Server酱) notifications."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import requests

from utils.user_info import get_current_time


def wx_send(key, text: str | None = None, desp: str | None = None):
    if not key or not str(key).strip():
        return
    url = f"https://sctapi.ftqq.com/{key}.send"
    current_time = get_current_time()
    data = {
        "text": f"{current_time}  {text or '签到成功！'}",
        "desp": desp or "",
    }
    response = requests.post(url, data=data, timeout=10)
    if response.status_code == 200:
        print("WX消息发送成功")
    else:
        print(f"WX消息发送失败，状态码: {response.status_code}")


def format_summary(results: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    success_lines: list[str] = []
    failed_lines: list[str] = []
    for item in results:
        name = str(item.get("name") or "未命名")
        status = str(item.get("status") or "")
        reason = str(item.get("reason") or "").strip()
        if status in {"success", "already_signed", "preview", "session_ok", "refreshed"}:
            extra = f"（{reason}）" if reason else ""
            success_lines.append(f"{name}成功{extra}")
        elif status == "skipped":
            continue
        else:
            failed_lines.append(f"{name}失败，原因：{reason or '未知错误'}")
    if not failed_lines:
        title = "全部签到成功"
    elif not success_lines:
        title = "全部失败"
    else:
        title = "部分失败"
    parts: list[str] = []
    if success_lines:
        parts.append("\n".join(success_lines))
    if failed_lines:
        parts.append("\n".join(failed_lines))
    return title, "\n\n".join(parts) or "无结果"


def send_summary_notification(wx_key, results):
    if not wx_key or not str(wx_key).strip():
        return
    title, desp = format_summary(results)
    wx_send(wx_key, text=title, desp=desp)
