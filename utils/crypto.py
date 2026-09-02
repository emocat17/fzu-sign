"""AES-128-CBC encryption of the encrypted ``param`` query values."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError as exc:  # pragma: no cover - exercised only on missing dependency
    raise SystemExit(
        "缺少 cryptography 依赖，请运行: python -m pip install cryptography"
    ) from exc

from utils.config import H5_AES_KEY, PLACEHOLDERS


def aes_query_value(value: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    encryption = config.get("encryption", {})
    if not isinstance(encryption, Mapping):
        encryption = {}
    key_text = str(encryption.get("key") or H5_AES_KEY)
    iv_text = str(encryption.get("iv") or key_text)
    if key_text in PLACEHOLDERS:
        key_text = H5_AES_KEY
    if iv_text in PLACEHOLDERS:
        iv_text = key_text
    key = key_text.encode("utf-8")
    iv = iv_text.encode("utf-8")
    if len(key) != 16 or len(iv) != 16:
        raise ValueError("AES key/iv 必须是 16 字节")
    plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    base64_value = base64.b64encode(ciphertext).decode("ascii")
    return quote(base64_value, safe="-_.!~*'()")
