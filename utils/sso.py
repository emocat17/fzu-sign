"""FZU SSO login used to refresh an expired yzsxg session Cookie."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import urljoin

from utils.config import PLACEHOLDERS, base_url, real_value, timeout_seconds

SSO_ORIGIN = "https://sso.fzu.edu.cn"
AUTHORIZE_PATH = "/livecloud/project/fzu/attn/oauth2/authorize.action"
INDEX_PATH = "/plug-in/livecloud/project/fzu/attn/index.action"
LOGIN_MARKERS = ("请先登录", "请登录", "未登录", "登录后操作", "先登录", "not logged", "login first")


def session_unauthenticated(exc: BaseException) -> bool:
    return any(marker in str(exc) for marker in LOGIN_MARKERS)


def auth_credentials(config: Mapping[str, Any]) -> tuple[str, str] | None:
    auth = config.get("auth", {})
    if not isinstance(auth, Mapping):
        return None
    username = auth.get("username")
    password = auth.get("password")
    if username is None or password is None:
        return None
    user_text = str(username).strip()
    pass_text = str(password)
    if user_text in PLACEHOLDERS or pass_text.strip() in PLACEHOLDERS:
        return None
    return user_text, pass_text


def auth_cookie(config: Mapping[str, Any]) -> str:
    auth = config.get("auth", {})
    if not isinstance(auth, Mapping):
        return ""
    cookie = auth.get("cookie")
    text = str(cookie).strip() if cookie is not None else ""
    return "" if text in PLACEHOLDERS else text


def encrypt_password(plain: str, croypto_b64: str) -> str:
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("缺少 cryptography 依赖，请运行: python -m pip install cryptography") from exc
    key = base64.b64decode(croypto_b64.strip())
    if len(key) not in (16, 24, 32):
        raise ValueError("SSO croypto 不是合法 AES 密钥")
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plain.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")


def _html_text(html: str, element_id: str) -> str:
    match = re.search(rf'id="{re.escape(element_id)}"[^>]*>([^<]*)</', html, re.I)
    if not match:
        raise ValueError(f"SSO 登录页缺少 {element_id}")
    return match.group(1).strip()


def parse_login_page(html: str) -> dict[str, str]:
    captcha_id = ""
    try:
        captcha_id = _html_text(html, "captchaId")
    except ValueError:
        captcha_id = ""
    second = ""
    try:
        second = _html_text(html, "sso-second")
    except ValueError:
        second = ""
    error_code = ""
    try:
        error_code = _html_text(html, "login-error-code")
    except ValueError:
        error_code = ""
    if captcha_id:
        raise ValueError("SSO 要求验证码，无法自动登录")
    if second:
        raise ValueError("SSO 要求二次验证，无法自动登录")
    return {
        "croypto": _html_text(html, "login-croypto"),
        "execution": _html_text(html, "login-page-flowkey"),
        "error_code": error_code,
    }


def cookie_header_from_jar(jar: CookieJar | Any, hosts: tuple[str, ...] = ("yzsxg.fzu.edu.cn",)) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for cookie in jar:
        domain = str(getattr(cookie, "domain", "") or "").lstrip(".").lower()
        if hosts and not any(domain == host or domain.endswith("." + host) for host in hosts):
            continue
        if cookie.name in seen:
            continue
        seen.add(cookie.name)
        parts.append(f"{cookie.name}={cookie.value}")
    return "; ".join(parts)


def _user_agent(config: Mapping[str, Any]) -> str:
    app = config.get("app", {})
    if isinstance(app, Mapping) and app.get("user_agent"):
        return str(app["user_agent"])
    return "Mozilla/5.0"


def apply_cookie(config: dict[str, Any], cookie: str) -> None:
    auth = config.setdefault("auth", {})
    if not isinstance(auth, dict):
        raise ValueError("auth 必须是 JSON 对象")
    auth["cookie"] = cookie


def login_and_cookie(config: Mapping[str, Any]) -> str:
    """Log in via FZU SSO and return the yzsxg Cookie header string."""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("缺少 requests 依赖，请运行: python -m pip install requests") from exc

    creds = auth_credentials(config)
    if creds is None:
        raise ValueError("未填写 auth.username / auth.password，无法自动刷新 Cookie")
    username, password = creds
    origin = base_url(config)
    service = f"{origin}/livecloud/project/fzu/attn/oauth2/callback.action"
    authorize = urljoin(origin + "/", AUTHORIZE_PATH.lstrip("/"))
    timeout = timeout_seconds(config)
    headers = {"User-Agent": _user_agent(config), "Accept": "text/html,application/xhtml+xml"}
    session = requests.Session()
    try:
        response = session.get(authorize, headers=headers, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400:
            response = session.get(
                f"{SSO_ORIGIN}/login",
                params={"service": service},
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
        response.raise_for_status()
        existing = cookie_header_from_jar(session.cookies)
        if existing and "login-croypto" not in response.text:
            return existing
        page = parse_login_page(response.text)
        payload = {
            "username": username,
            "password": encrypt_password(password, page["croypto"]),
            "type": "UsernamePassword",
            "_eventId": "submit",
            "geolocation": "",
            "execution": real_value(page["execution"], "SSO execution"),
            "croypto": page["croypto"],
            "captcha_code": "",
        }
        posted = session.post(
            response.url,
            data=payload,
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
            allow_redirects=True,
        )
        posted.raise_for_status()
        if "sso.fzu.edu.cn/login" in posted.url:
            extra = ""
            try:
                failed = parse_login_page(posted.text)
                if failed.get("error_code"):
                    extra = f"（错误码 {failed['error_code']}）"
            except ValueError:
                extra = ""
            raise ValueError(f"SSO 登录失败{extra}，请检查 auth.username / auth.password")
        auth = config.get("auth", {})
        token = ""
        if isinstance(auth, Mapping) and auth.get("token") not in (None, *PLACEHOLDERS):
            token = str(auth.get("token") or "").strip()
        if token:
            session.get(
                urljoin(origin + "/", INDEX_PATH.lstrip("/")),
                params={"token": token, "contextPath": ""},
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
        cookie = cookie_header_from_jar(session.cookies)
        if not cookie:
            cookie = cookie_header_from_jar(session.cookies, hosts=())
        if not cookie:
            raise ValueError("SSO 登录成功但未拿到 yzsxg Cookie")
        return cookie
    except requests.RequestException as exc:
        raise ValueError(f"SSO 登录网络错误: {exc}") from exc
