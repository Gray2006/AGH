from __future__ import annotations

from agh.crypto import KeyRing
from agh.forgetting import ForgettingRegistry, residual_scan, verify_forgetting


def registry() -> ForgettingRegistry:
    ring = KeyRing.with_secret("k1", b"x" * 16)
    return ForgettingRegistry(ring.get("k1"), clock=lambda: 1000)


def test_forget_and_verify() -> None:
    reg = registry()
    tombstone = reg.forget("rec-1", {"secret": "abc"}, reason="用户要求")
    assert reg.is_forgotten("rec-1")
    assert reg.verify(tombstone)
    assert tombstone.content_hash


def test_tampered_tombstone_fails() -> None:
    reg = registry()
    tombstone = reg.forget("rec-1", {"secret": "abc"})
    bad = type(tombstone)(**{**tombstone.as_dict(), "reason": "改过"})
    assert not reg.verify(bad)


def test_residual_scan_finds_record_and_edge() -> None:
    records = [{"id": "a", "ref": "rec-1"}, {"id": "b", "ref": "other"}]
    edges = [("rec-1", "x")]
    assert residual_scan(["rec-1"], records, edges) == ["rec-1"]
    assert residual_scan(["rec-1"], [{"id": "b"}], []) == []


def test_verify_forgetting_ok_and_residual() -> None:
    reg = registry()
    reg.forget("rec-1", {"secret": "abc"})
    clean = verify_forgetting(reg, [{"id": "b"}], [])
    assert clean["ok"] is True
    dirty = verify_forgetting(reg, [{"id": "b", "ref": "rec-1"}], [])
    assert dirty["ok"] is False
    assert dirty["residuals"] == ["rec-1"]
