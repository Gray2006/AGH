from __future__ import annotations

import pytest

from agh.netutil import UnsafeUrl, ensure_http_url, open_http


def test_accepts_http_and_https() -> None:
    assert ensure_http_url("http://example.com/x") == "http://example.com/x"
    assert ensure_http_url("https://api.example.com/v1") == "https://api.example.com/v1"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "data:text/plain,hi",
        "/local/path",
        "https://",
    ],
)
def test_rejects_unsafe_schemes(url: str) -> None:
    with pytest.raises(UnsafeUrl):
        ensure_http_url(url)


def test_open_http_checks_before_opening() -> None:
    """校验在发请求之前，file:// 不会被打开。"""
    with pytest.raises(UnsafeUrl):
        open_http("file:///etc/passwd")
