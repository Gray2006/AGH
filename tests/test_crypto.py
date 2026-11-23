from __future__ import annotations

import pytest

from agh.contracts import SignedEnvelope, TrustLevel
from agh.crypto import (
    EnvelopeVerifier,
    KeyRing,
    ProvenanceError,
    ProvenanceGateway,
    SettlementVerifier,
    derive_trust,
    sign_settlement,
)

SECRET = b"unit-test-secret"
KID = "gw-1"


def make_gateway(clock=None) -> tuple[ProvenanceGateway, KeyRing]:
    ring = KeyRing.with_secret(KID, SECRET)
    return ProvenanceGateway(ring, KID, clock=clock), ring


def test_valid_envelope_verifies() -> None:
    gw, ring = make_gateway()
    env = gw.issue(
        payload={"a": 1},
        producer_id="c1",
        producer_kind="child",
        parent_contract_id="ct1",
        trust=TrustLevel.LOCAL,
    )
    prov = EnvelopeVerifier(ring).verify(env)
    assert prov.producer_id == "c1"
    assert prov.trust == int(TrustLevel.LOCAL)


def test_forged_trust_rejected_by_signature() -> None:
    gw, ring = make_gateway()
    env = gw.issue(
        payload={"a": 1},
        producer_id="c1",
        producer_kind="child",
        parent_contract_id="ct1",
        trust=TrustLevel.LOCAL,
    )
    raw = env.model_dump(mode="json")
    raw["provenance"]["trust"] = int(TrustLevel.TRUSTED)  # 子级越权抬等级
    forged = SignedEnvelope.model_validate(raw)
    verifier = EnvelopeVerifier(ring)
    with pytest.raises(ProvenanceError) as exc:
        verifier.verify(forged)
    assert exc.value.code == "bad_sig"
    assert verifier.stats.failure_count == 1


def test_tampered_payload_rejected_before_signature() -> None:
    gw, ring = make_gateway()
    env = gw.issue(
        payload={"a": 1},
        producer_id="c1",
        producer_kind="child",
        parent_contract_id="ct1",
        trust=TrustLevel.LOCAL,
    )
    raw = env.model_dump(mode="json")
    raw["payload"]["a"] = 2
    with pytest.raises(ProvenanceError) as exc:
        EnvelopeVerifier(ring).verify(SignedEnvelope.model_validate(raw))
    assert exc.value.code == "payload_hash_mismatch"


def test_replay_rejected() -> None:
    gw, ring = make_gateway()
    env = gw.issue(
        payload={"a": 1},
        producer_id="c1",
        producer_kind="child",
        parent_contract_id="ct1",
        trust=TrustLevel.LOCAL,
    )
    verifier = EnvelopeVerifier(ring)
    verifier.verify(env)
    with pytest.raises(ProvenanceError) as exc:
        verifier.verify(env)
    assert exc.value.code == "replay_nonce"


def test_stale_seq_rejected() -> None:
    gw, ring = make_gateway()
    first = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    second = gw.issue(
        payload={"a": 2}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    verifier = EnvelopeVerifier(ring)
    verifier.verify(second)
    with pytest.raises(ProvenanceError) as exc:
        verifier.verify(first)  # 先验后签的旧消息
    assert exc.value.code == "replay_nonce" or exc.value.code == "stale_seq"


def test_revoked_key_rejected() -> None:
    gw, ring = make_gateway()
    env = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    ring.revoke(KID)
    with pytest.raises(ProvenanceError) as exc:
        EnvelopeVerifier(ring).verify(env)
    assert exc.value.code == "revoked_kid"


def test_unknown_kid_rejected() -> None:
    gw, _ring = make_gateway()
    env = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    other = KeyRing.with_secret("other", b"x")
    with pytest.raises(ProvenanceError) as exc:
        EnvelopeVerifier(other).verify(env)
    assert exc.value.code == "unknown_kid"


def test_expired_key_rejected() -> None:
    ring = KeyRing()
    ring.register(KID, SECRET, not_after_ms=1000)
    gw = ProvenanceGateway(ring, KID, clock=lambda: 500)
    env = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    with pytest.raises(ProvenanceError) as exc:
        EnvelopeVerifier(ring, clock=lambda: 2000).verify(env)
    assert exc.value.code == "expired_kid"


def test_taint_propagation_takes_min() -> None:
    assert derive_trust([TrustLevel.TRUSTED, TrustLevel.LOCAL]) == TrustLevel.LOCAL
    assert derive_trust([TrustLevel.TRUSTED, TrustLevel.VALIDATED]) == TrustLevel.VALIDATED
    assert derive_trust([]) == TrustLevel.QUARANTINED


def test_settlement_replay_and_version_guard() -> None:
    ring = KeyRing.with_secret(KID, SECRET)
    judge_hash = "a" * 64
    msg = sign_settlement(
        keyring=ring, kid=KID, settlement_id="st1", epoch=1, seq=1,
        judge_version_hash=judge_hash, amount_usd=0.5,
    )
    verifier = SettlementVerifier(ring, judge_hash)
    verifier.verify(msg)
    with pytest.raises(ProvenanceError) as exc:
        verifier.verify(msg)
    assert exc.value.code == "replay_nonce"

    wrong_version = sign_settlement(
        keyring=ring, kid=KID, settlement_id="st1", epoch=1, seq=2,
        judge_version_hash="b" * 64, amount_usd=0.5,
    )
    with pytest.raises(ProvenanceError) as exc:
        SettlementVerifier(ring, judge_hash).verify(wrong_version)
    assert exc.value.code == "judge_version_mismatch"

def _ed_private() -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return Ed25519PrivateKey.generate().private_bytes_raw()


def test_ed25519_gateway_roundtrip() -> None:
    ring = KeyRing.with_ed25519("ed-1", _ed_private())
    gw = ProvenanceGateway(ring, "ed-1")
    env = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    prov = EnvelopeVerifier(ring).verify(env)
    assert prov.kid == "ed-1"
    assert prov.trust == int(TrustLevel.LOCAL)


def test_ed25519_tampered_sig_rejected() -> None:
    ring = KeyRing.with_ed25519("ed-1", _ed_private())
    gw = ProvenanceGateway(ring, "ed-1")
    env = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    raw = env.model_dump(mode="json")
    raw["provenance"]["sig"] = "00" * 64
    with pytest.raises(ProvenanceError) as exc:
        EnvelopeVerifier(ring).verify(SignedEnvelope.model_validate(raw))
    assert exc.value.code == "bad_sig"


def test_key_rotation_overlap_then_expiry() -> None:
    now = 1_000_000
    ring = KeyRing.with_secret("old", b"x" * 16)
    gw_old = ProvenanceGateway(ring, "old", clock=lambda: now)
    env_old = gw_old.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    ring.rotate("old", "new", secret=b"y" * 16, overlap_ms=1_000, now_ms=now)

    # 重叠窗口内旧密钥仍可验
    EnvelopeVerifier(ring, clock=lambda: now + 500).verify(env_old)
    # 窗口过后旧密钥过期
    with pytest.raises(ProvenanceError) as exc:
        EnvelopeVerifier(ring, clock=lambda: now + 2_000).verify(env_old)
    assert exc.value.code == "expired_kid"

    gw_new = ProvenanceGateway(ring, "new", clock=lambda: now + 2_000)
    env_new = gw_new.issue(
        payload={"a": 2}, producer_id="c2", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    EnvelopeVerifier(ring, clock=lambda: now + 2_000).verify(env_new)


def test_rotation_to_ed25519() -> None:
    ring = KeyRing.with_secret("old", b"x" * 16)
    ring.rotate("old", "new", private_bytes=_ed_private(), overlap_ms=0, now_ms=0)
    gw = ProvenanceGateway(ring, "new", clock=lambda: 0)
    env = gw.issue(
        payload={"a": 1}, producer_id="c1", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    EnvelopeVerifier(ring, clock=lambda: 0).verify(env)
