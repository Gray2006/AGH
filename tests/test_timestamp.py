from __future__ import annotations

import json
from pathlib import Path

import pytest

from agh.timestamp import (
    HmacTimestampAuthority,
    HttpTimestampAuthority,
    TimestampError,
    TimestampToken,
    anchor_log,
    verify_anchor,
)


def test_hmac_tsa_roundtrip() -> None:
    tsa = HmacTimestampAuthority(clock=lambda: 1000)
    token = tsa.stamp("abc")
    assert token.digest == "abc"
    assert token.issued_at_ms == 1000
    assert tsa.verify(token)


def test_hmac_tsa_rejects_tampered_token() -> None:
    tsa = HmacTimestampAuthority(clock=lambda: 1000)
    token = tsa.stamp("abc")
    bad = TimestampToken(**{**token.as_dict(), "issued_at_ms": 2000})
    assert not tsa.verify(bad)


def test_anchor_log_roundtrip(tmp_path: Path) -> None:
    tsa = HmacTimestampAuthority(clock=lambda: 1000)
    path = tmp_path / "anchor.json"
    token = anchor_log("head-hash", tsa, path)
    assert json.loads(path.read_text(encoding="utf-8"))["digest"] == "head-hash"
    assert verify_anchor(path, tsa) == token


def test_anchor_rejects_wrong_tsa(tmp_path: Path) -> None:
    tsa = HmacTimestampAuthority(secret=b"a", clock=lambda: 1000)
    path = tmp_path / "anchor.json"
    anchor_log("head", tsa, path)
    with pytest.raises(TimestampError):
        verify_anchor(path, HmacTimestampAuthority(secret=b"b"))


def test_http_tsa_with_fake_transport() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def transport(method: str, url: str, payload: dict | None) -> dict:
        calls.append((method, url, payload))
        if url.endswith("/verify"):
            return {"valid": True}
        return {"issued_at_ms": 123, "token": "tok", "sig": "sig", "authority": "remote"}

    tsa = HttpTimestampAuthority("https://tsa.example/api", transport=transport)
    token = tsa.stamp("digest")
    assert token.token == "tok"
    assert tsa.verify(token)
    assert calls[0][1] == "https://tsa.example/api"
    assert calls[1][1].endswith("/verify")
