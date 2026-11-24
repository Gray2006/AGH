from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from agh.anchoring import Anchor, AnchorStore, anchor_log, check_log, digest_of, verify_anchor
from agh.crypto import KeyRing
from agh.eventlog import EventLog, LogTampered
from agh.pipeline import DEV_KID, DEV_SECRET


def _log(tmp_path: Path, n: int = 3) -> EventLog:
    log = EventLog(tmp_path / "events.jsonl")
    for i in range(n):
        log.append("test.event", {"i": i})
    return log


def test_unsigned_anchor_detects_edit(tmp_path: Path) -> None:
    log = _log(tmp_path)
    anchor = anchor_log(log, label="t")
    assert check_log(log, anchor) is False  # 顺序完整，但未签名

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    lines[1] = re.sub(r'"i":\s*1', '"i": 99', lines[1])
    (tmp_path / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LogTampered):
        check_log(log, anchor)


def test_anchor_detects_truncation(tmp_path: Path) -> None:
    log = _log(tmp_path)
    anchor = anchor_log(log)
    (tmp_path / "events.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(LogTampered):
        check_log(log, anchor)


def test_signed_anchor_verifies(tmp_path: Path) -> None:
    keyring = KeyRing.with_ed25519(DEV_KID, hashlib.sha256(DEV_SECRET).digest())
    log = _log(tmp_path)
    anchor = anchor_log(log, key=keyring.get(DEV_KID))
    assert verify_anchor(anchor, keyring)
    assert check_log(log, anchor, keyring=keyring) is True


def test_tampered_anchor_fails_signature(tmp_path: Path) -> None:
    keyring = KeyRing.with_ed25519(DEV_KID, hashlib.sha256(DEV_SECRET).digest())
    log = _log(tmp_path)
    anchor = anchor_log(log, key=keyring.get(DEV_KID))
    forged = Anchor(
        head="0" * 64,
        size=anchor.size,
        log_path=anchor.log_path,
        label=anchor.label,
        created_at=anchor.created_at,
        signer=anchor.signer,
        signature=anchor.signature,
    )
    assert not verify_anchor(forged, keyring)
    with pytest.raises(LogTampered):
        check_log(log, forged, keyring=keyring)


def test_anchor_signed_by_wrong_key_fails(tmp_path: Path) -> None:
    signer = KeyRing.with_ed25519(DEV_KID, hashlib.sha256(DEV_SECRET).digest())
    other = KeyRing.with_ed25519(DEV_KID, hashlib.sha256(b"another-secret").digest())
    log = _log(tmp_path)
    anchor = anchor_log(log, key=signer.get(DEV_KID))
    assert not verify_anchor(anchor, other)


def test_anchor_store_latest_and_check(tmp_path: Path) -> None:
    log = _log(tmp_path)
    store = AnchorStore(tmp_path / "anchors.jsonl")
    store.append(anchor_log(log, label="v1"))
    log.append("test.event", {"i": 3})
    store.append(anchor_log(log, label="v2"))
    assert [a.label for a in store.read()] == ["v1", "v2"]
    assert store.latest(str(log.path)).label == "v2"  # type: ignore[union-attr]
    assert store.check(log) is False
    assert len(digest_of(store.read()[0])) == 64
