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
    personal_wx_key,
    save_user_auth,
    should_auto_send,
    summary_wx_key,
    user_configs,
    user_enabled,
    user_label,
    validate_user_config,
)
from utils.log import write_log
from utils.sso import (
    apply_session,
    auth_cookie,
    auth_token_value,
    can_refresh_session,
    login_and_session,
    session_unauthenticated,
)


def _ca_is_no(config: Mapping[str, Any]) -> str:
    clock_in = config.get("clock_in", {})
    return str(clock_in.get("caIsNo", "0")) if isinstance(clock_in, Mapping) else "0"


def classify_reason(exc: BaseException) -> str:
    message = str(exc)
    lowered = message.lower()
    if session_unauthenticated(exc) or "cookie" in lowered or "未登录" in message:
        return "cookie错误"
    if "sso 暂时不可用" in lowered:
        return "网络超时"
    if "sso" in lowered or "auth.username" in message or "auth.password" in message:
        return "登录失败"
    if "auth.token" in message or "缺少 token" in message:
        return "token错误"
    if "时间窗口" in message:
        return "不在签到窗口"
    if "校区" in message:
        return "定位不在校区"
    if "网络" in message or "timed out" in lowered or "timeout" in lowered:
        return "网络超时"
    if "请填写" in message:
        return f"配置缺项：{message}"
    return message


def notify_signed(config: Mapping[str, Any], text: str, desp: str) -> None:
    key = personal_wx_key(config)
    if not key:
        return
    try:
        from utils.notification import wx_send

        wx_send(key, text=text, desp=desp)
    except Exception as exc:
        write_log(f"[通知] 发送失败，已跳过：{exc}", error=True)


def notify_summary(config: Mapping[str, Any], results: list[dict[str, Any]]) -> None:
    key = summary_wx_key(config)
    if not key:
        return
    try:
        from utils.notification import send_summary_notification

        send_summary_notification(key, results)
    except Exception as exc:
        write_log(f"[通知] 汇总发送失败，已跳过：{exc}", error=True)


def print_preview(config: Mapping[str, Any], init_data: Mapping[str, Any], timestamp: int) -> None:
    write_log(f"[{user_label(config)}]")
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


def notify_cookie_refreshed(config: Mapping[str, Any]) -> None:
    title = f"晚点名 · Cookie 已刷新 · {user_label(config)}"
    desp = "Cookie/token 已更新并写回 data.json。窗口外探活完成，晚上可直接签到。"
    notify_signed(config, title, desp)
    key = summary_wx_key(config)
    if key and not personal_wx_key(config):
        try:
            from utils.notification import wx_send

            wx_send(key, text=title, desp=desp)
        except Exception as exc:
            write_log(f"[通知] 发送失败，已跳过：{exc}", error=True)


def refresh_session_cookie(config: dict[str, Any], path: Path, *, notify: bool = False) -> None:
    cookie, token = login_and_session(config)
    apply_session(config, cookie, token)
    save_user_auth(path, user_label(config), cookie, token)
    extra = "和 token" if token else ""
    write_log(f"[{user_label(config)}] 已刷新 Cookie{extra} 并写回 {path.name}")
    if notify:
        notify_cookie_refreshed(config)


def with_fresh_session(config: dict[str, Any], path: Path, fetch, *, notify_refresh: bool = False):
    refreshed = False
    missing = (not auth_cookie(config) or not auth_token_value(config)) and can_refresh_session(config)
    if missing:
        write_log(f"[{user_label(config)}] Cookie/token 缺失，正在自动登录补齐…")
        refresh_session_cookie(config, path, notify=notify_refresh)
        refreshed = True
    try:
        return fetch(), refreshed
    except ValueError as exc:
        if not session_unauthenticated(exc) or not can_refresh_session(config):
            raise
        write_log(f"[{user_label(config)}] Cookie/token 失效，正在自动重新登录…")
        refresh_session_cookie(config, path, notify=notify_refresh)
        return fetch(), True


def check_session(config: dict[str, Any], path: Path | None = None, *, notify_refresh: bool = False) -> tuple[int, str, bool]:
    """Read-only session precheck: validates init + server timestamp."""
    try:
        init_data, refreshed = with_fresh_session(
            config,
            path or DEFAULT_CONFIG,
            lambda: protocol.fetch_init(config),
            notify_refresh=notify_refresh,
        )
        protocol.fetch_server_timestamp(config)
    except ValueError as exc:
        reason = classify_reason(exc)
        write_log(f"[{user_label(config)}] 会话异常: {exc}", error=True)
        if session_unauthenticated(exc):
            notify_signed(
                config,
                "晚点名 · 会话失效",
                f"[{user_label(config)}] {reason}：{exc}",
            )
        return 2, reason, False
    write_log(f"[{user_label(config)}] 会话有效：init.action 与 currentTimestamp.action 均返回成功")
    params = init_data.get("paramsData", {})
    if isinstance(params, Mapping):
        write_log(f"签到窗口: {params.get('FStartTime', '?')} - {params.get('FEndTime', '?')}")
    write_log(f"当前状态: {'已签到（不重复）' if protocol.status_success(init_data) else '未签到'}")
    return 0, "", refreshed


def run(config: Mapping[str, Any], send: bool, path: Path | None = None) -> tuple[int, str]:
    runtime = dict(config)
    init_data, refreshed = with_fresh_session(
        runtime,
        path or DEFAULT_CONFIG,
        lambda: protocol.fetch_init(runtime),
        notify_refresh=send,
    )
    timestamp = protocol.fetch_server_timestamp(runtime)
    config = runtime
    if not send:
        print_preview(config, init_data, timestamp)
        write_log(f"[{user_label(config)}] DRY-RUN：未发送 check.action 或 clockIn.action。")
        return 0, "preview"

    request_config = config.get("request", {})
    if not isinstance(request_config, Mapping) or request_config.get("enabled") is not True:
        raise ValueError("request.enabled 必须明确设置为 true")
    params = init_data.get("paramsData", {})
    in_window = isinstance(params, Mapping) and schedule.in_time_window(
        timestamp, params.get("FStartTime"), params.get("FEndTime")
    )
    if not in_window:
        write_log(f"[{user_label(config)}] 当前不在签到时间窗口内，已完成会话探活，不提交签到。")
        if refreshed:
            return 0, "refreshed"
        return 0, "session_ok"
    if protocol.status_success(init_data):
        write_log(f"[{user_label(config)}] 服务端已显示签到成功，停止，不重复提交。")
        notify_signed(config, f"晚点名已签到 · {user_label(config)}", "服务端状态为成功/处理中，无需重复提交。")
        return 0, "already_signed"
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
    write_log(f"[{user_label(config)}] 将提交一次真实签到请求到 {api_url(config, 'clockIn.action')}")
    write_log(f"[{user_label(config)}] 定位命中校区：{matched_name or '（未识别）'}；提交字段：{', '.join(clock_payload)}")
    query = crypto.aes_query_value(clock_payload, config)
    result = net.unwrap_success(
        net.request_json(config, "clockIn.action", "GET", query={"param": query}), "clockIn.action"
    )
    write_log(f"[{user_label(config)}] clockIn.action 返回结构：{protocol.response_shape(result)}")
    write_log(f"[{user_label(config)}] 已完成一次请求；请在 App 页面核对服务端状态。")
    notify_signed(
        config,
        f"晚点名签到成功 · {user_label(config)}",
        f"定位命中校区：{matched_name or '未知'}；服务端已接受请求。",
    )
    return 0, "success"


def _result(name: str, status: str, code: int, reason: str = "") -> dict[str, Any]:
    return {"name": name, "status": status, "code": code, "reason": reason}


def handle_user(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    name = user_label(config)
    if not user_enabled(config):
        write_log(f"[{name}] 已跳过（enabled=false）")
        return _result(name, "skipped", 0, "未启用")
    try:
        if args.refresh_cookie:
            if not can_refresh_session(config):
                raise ValueError("未填写 Cookie 或账号密码，无法自动刷新会话")
            refresh_session_cookie(config, args.config, notify=True)
            return _result(name, "refreshed", 0, "已刷新Cookie/token")
        validate_user_config(config)
        if args.check:
            code, reason, refreshed = check_session(config, args.config, notify_refresh=True)
            if code == 0:
                return _result(name, "refreshed" if refreshed else "session_ok", 0, "已刷新Cookie/token" if refreshed else "")
            return _result(name, "failed", code, reason)
        send = False if args.dry_run else should_auto_send(config)
        code, status = run(config, send=send, path=args.config)
        if args.dry_run or not send:
            return _result(name, "preview", 0)
        if status == "refreshed":
            return _result(name, "refreshed", code, "已刷新Cookie/token")
        if status == "session_ok":
            return _result(name, "session_ok", code, "会话有效（未到签到窗口）")
        if status == "already_signed":
            return _result(name, "already_signed", code, "已签到")
        return _result(name, status, code)
    except (ValueError, TypeError, KeyError) as exc:
        reason = classify_reason(exc)
        write_log(f"[{name}] 配置/协议错误: {exc}", error=True)
        notify_signed(config, f"晚点名失败 · {name}", f"原因：{reason}\n{exc}")
        return _result(name, "failed", 2, reason)


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
        help="只读会话预检：校验 init/时间戳；会话失效时自动刷新 Cookie/token",
    )
    parser.add_argument(
        "--refresh-cookie",
        action="store_true",
        help="强制刷新 Cookie/token 并写回 data.json，不签到",
    )
    args = parser.parse_args(argv)
    if not args.config.exists():
        write_log(f"找不到配置文件: {args.config}", error=True)
        write_log("首次使用请先复制模板再填写：copy data.json.example data.json", error=True)
        return 2
    try:
        root = load_config(args.config)
        configs = user_configs(root, args.user)
    except (ValueError, TypeError, KeyError) as exc:
        write_log(f"配置/协议错误: {exc}", error=True)
        return 2
    results: list[dict[str, Any]] = []
    for index, config in enumerate(configs):
        if index:
            print()
        results.append(handle_user(config, args))
    if not args.dry_run:
        actionable = [item for item in results if item.get("status") not in {"session_ok", "skipped", "preview"}]
        if actionable:
            notify_summary(configs[0] if configs else root, results)
    failed = any(item["code"] != 0 for item in results)
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
