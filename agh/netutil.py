"""HTTP 请求的小工具：统一校验 scheme，禁止 file:// 等本地协议。

`urllib.request.urlopen` 默认接受 `file:`、`ftp:` 等 scheme。如果 URL 来自
用户输入或配置，攻击者可以诱导读本地文件。三处网络调用都走这里。
"""

from __future__ import annotations

import urllib.request
from typing import Any
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")


class UnsafeUrl(ValueError):
    """URL 的 scheme 不在允许列表里。"""


def ensure_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrl(f"只允许 http/https，收到 {parsed.scheme or '(空)'}: {url[:80]}")
    if not parsed.netloc:
        raise UnsafeUrl(f"缺少主机名：{url[:80]}")
    return url


def open_http(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str | None = None,
    timeout: float = 30.0,
) -> Any:
    """带 scheme 校验的 urlopen。返回 response 对象（调用方负责 read）。"""
    ensure_http_url(url)
    req = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method
    )
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310 - scheme 已校验


__all__ = ["ALLOWED_SCHEMES", "UnsafeUrl", "ensure_http_url", "open_http"]
