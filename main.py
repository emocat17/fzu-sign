#!/usr/bin/env python3
"""One-shot authorized late-rollcall runner.

Plain ``python main.py`` signs in automatically when ``request.enabled`` is
true; otherwise it performs a read-only preview. Submission is guarded by the
server window, the not-yet-signed status and the location-range check, and it
never fabricates a location or bypasses server checks. The reusable logic
lives in the ``utils`` package.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from utils import crypto, net, payload, protocol, schedule
from utils.config import (
    DEFAULT_CONFIG,
    api_url,
    load_config,
    should_auto_send,
    user_configs,
    user_label,
)


def _ca_is_no(config: Mapping[str, Any]) -> str:
    clock_in = config.get("clock_in", {})
    return str(clock_in.get("caIsNo", "0")) if isinstance(clock_in, Mapping) else "0"


def notify_signed(config: Mapping[str, Any], text: str, desp: str) -> None:
    """Send a WeChat push after a sign-in outcome, best-effort.

    Reads the Server酱 key from the top-level ``WXKey`` field; skips silently
    when it is absent. Imported lazily so a notification failure never breaks
    the core sign-in flow.
    """
    key = config.get("WXKey")
    if not key or not str(key).strip():
        return
    try:
        from utils.notification import wx_send

        wx_send(str(key), text=text, desp=desp)
    except Exception as exc:
        print(f"[通知] 发送失败，已跳过：{exc}", file=sys.stderr)


def print_preview(config: Mapping[str, Any], init_data: Mapping[str, Any], timestamp: int) -> None:
    print(f"[{user_label(config)}]")
    latitude, longitude, address = payload.location_values(config)
    clock_payload = payload.build_clock_in_payload(
        init_data,
        latitude=latitude,
        longitude=longitude,
        address=address,
        server_timestamp=timestamp,
        ca_is_no=_ca_is_no(config),
    )
    check_payload = payload.build_check_payload(init_data, latitude, longitude)
    params = init_data.get("paramsData", {})
    status = init_data.get("statusData")
    print("协议预览（未调用 check.action/clockIn.action）:")
    print(f"  clockIn URL: {api_url(config, 'clockIn.action')}?param=<encrypted>")
    print("  method: GET")
    print("  headers: token, User-Agent")
    print(f"  check fields: {', '.join(check_payload)}")
    print(f"  clockIn fields: {', '.join(clock_payload)}")
    print(f"  init response shape: {protocol.response_shape(init_data)}")
    print(f"  server timestamp type: {type(timestamp).__name__}")
    print(f"  current status: {'already-signed' if protocol.status_success(init_data) else 'not-success'}")
    if isinstance(params, Mapping):
        print(f"  time window: {params.get('FStartTime', '<missing>')} - {params.get('FEndTime', '<missing>')}")
    print("  encrypted check query: <redacted>")
    print("  encrypted clockIn query: <redacted>")
    _ = status


def check_session(config: Mapping[str, Any]) -> int:
    """Read-only session precheck: validates init + server timestamp.

    On success prints the window/status. If the server says the session is not
    logged in (dead Cookie/token), pushes a WeChat warning via WXKey so the user
    refreshes it before the sign-in window opens.
    """
    try:
        init_data = protocol.fetch_init(config)
        protocol.fetch_server_timestamp(config)
    except ValueError as exc:
        message = str(exc)
        print(f"[{user_label(config)}] 会话异常: {message}", file=sys.stderr)
        if "未登录" in message:
            notify_signed(
                config,
                "晚点名 · 会话失效",
                f"[{user_label(config)}] Cookie/token 已失效：请在签到前重新登录，把最新的 Cookie 与 token 填回 data.json 对应用户的 auth.cookie / auth.token。",
            )
        return 2
    print(f"[{user_label(config)}] 会话有效：init.action 与 currentTimestamp.action 均返回成功")
    params = init_data.get("paramsData", {})
    if isinstance(params, Mapping):
        print(f"签到窗口: {params.get('FStartTime', '?')} - {params.get('FEndTime', '?')}")
    print(f"当前状态: {'已签到（不重复）' if protocol.status_success(init_data) else '未签到'}")
    return 0


def run(config: Mapping[str, Any], send: bool) -> int:
    init_data = protocol.fetch_init(config)
    timestamp = protocol.fetch_server_timestamp(config)
    if not send:
        print_preview(config, init_data, timestamp)
        print(f"\n[{user_label(config)}] DRY-RUN：未发送 check.action 或 clockIn.action。")
        return 0

    request_config = config.get("request", {})
    if not isinstance(request_config, Mapping) or request_config.get("enabled") is not True:
        raise ValueError("request.enabled 必须明确设置为 true")
    if protocol.status_success(init_data):
        print(f"[{user_label(config)}] 服务端已显示签到成功，停止，不重复提交。")
        notify_signed(config, f"晚点名已签到 · {user_label(config)}", "服务端状态为成功/处理中，无需重复提交。")
        return 0
    params = init_data.get("paramsData", {})
    if not isinstance(params, Mapping) or not schedule.in_time_window(
        timestamp, params.get("FStartTime"), params.get("FEndTime")
    ):
        raise ValueError("当前不在服务端返回的签到时间窗口内，停止发送")
    latitude, longitude, address = payload.location_values(config)
    check_query = crypto.aes_query_value(payload.build_check_payload(init_data, latitude, longitude), config)
    check_data = net.unwrap_success(
        net.request_json(config, "check.action", "GET", query={"param": check_query}), "check.action"
    )
    if not isinstance(check_data, list) or not check_data:
        raise ValueError("check.action 未返回匹配校区，停止发送")
    matched = check_data[0] if isinstance(check_data[0], Mapping) else None
    clock_payload = payload.build_clock_in_payload(
        init_data,
        latitude=latitude,
        longitude=longitude,
        address=address,
        server_timestamp=timestamp,
        ca_is_no=_ca_is_no(config),
        matched_campus=matched,
    )
    matched_name = str(matched.get("title") or matched.get("name") or matched.get("FName") or "") if matched else ""
    print(f"[{user_label(config)}] 将提交一次真实签到请求到 {api_url(config, 'clockIn.action')}")
    print(f"[{user_label(config)}] 定位命中校区：{matched_name or '（未识别）'}；提交字段：{', '.join(clock_payload)}")
    query = crypto.aes_query_value(clock_payload, config)
    result = net.unwrap_success(
        net.request_json(config, "clockIn.action", "GET", query={"param": query}), "clockIn.action"
    )
    print(f"[{user_label(config)}] clockIn.action 返回结构：{protocol.response_shape(result)}")
    print(f"[{user_label(config)}] 已完成一次请求；请在 App 页面核对服务端状态。")
    notify_signed(
        config,
        f"晚点名签到成功 · {user_label(config)}",
        f"定位命中校区：{matched_name or '未知'}；服务端已接受请求。",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="晚点名签到：request.enabled=true 时一键签到，否则只读预览")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--user", type=str, help="指定要操作的用户名称（可选，多用户模式）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="即使 request.enabled=true 也只做只读预览，不发送签到",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只读会话预检：校验 init/时间戳；会话失效时用 WXKey 推送提醒",
    )
    args = parser.parse_args(argv)
    if not args.config.exists():
        print(f"找不到配置文件: {args.config}", file=sys.stderr)
        print("首次使用请先复制模板再填写：copy data.json.example data.json", file=sys.stderr)
        return 2
    try:
        root = load_config(args.config)
        configs = user_configs(root, args.user)
    except (ValueError, TypeError, KeyError) as exc:
        print(f"配置/协议错误: {exc}", file=sys.stderr)
        return 2
    failed = 0
    for index, config in enumerate(configs):
        if index:
            print()
        try:
            if args.check:
                code = check_session(config)
            else:
                code = run(config, send=False if args.dry_run else should_auto_send(config))
        except (ValueError, TypeError, KeyError) as exc:
            print(f"[{user_label(config)}] 配置/协议错误: {exc}", file=sys.stderr)
            code = 2
        if code != 0:
            failed = code
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
