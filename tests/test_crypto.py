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
