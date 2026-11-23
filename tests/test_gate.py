from __future__ import annotations

from pathlib import Path

from agh.contracts import TrustLevel
from agh.crypto import EnvelopeVerifier, KeyRing, ProvenanceGateway
from agh.gate import (
    MemoryRecord,
    MemoryStore,
    RetrievalGate,
    RiskModel,
    WriteGate,
    promotion_decision,
    reuse_decision,
    risk_score,
)

SECRET = b"gate-test-secret"


def make_gate(frozen_src: Path):
    ring = KeyRing.with_secret("gw", SECRET)
    gateway = ProvenanceGateway(ring, "gw")
    verifier = EnvelopeVerifier(ring)
    model = RiskModel.from_frozen(frozen_src)
    store = MemoryStore()
    return ring, gateway, verifier, model, store, WriteGate(verifier, model, store)


def test_low_risk_admitted(frozen_src: Path) -> None:
    _, gateway, _, _, store, gate = make_gate(frozen_src)
    env = gateway.issue(
        payload={"content": {"edges": [], "speculative_links": 0}},
        producer_id="c1", producer_kind="child", parent_contract_id="ct",
        trust=TrustLevel.LOCAL,
    )
    admission = gate.admit(env, record_id="c1")
    assert admission.admitted
    assert admission.record.trust == int(TrustLevel.LOCAL)
    assert store.exists("c1")


def test_high_risk_quarantined_and_not_admitted(frozen_src: Path) -> None:
    _, gateway, _, model, store, gate = make_gate(frozen_src)
    env = gateway.issue(
        payload={
            "content": {
                "edges": [["A", "B"]],
                "verified_edges": [],
                "speculative_links": 1,
                "external_refs": 2,
            }
        },
        producer_id="c1", producer_kind="child", parent_contract_id="ct",
        trust=TrustLevel.LOCAL,
    )
    admission = gate.admit(env, record_id="c1")
    assert not admission.admitted
    assert admission.reason == "quarantined"
    assert "c1" in gate.quarantine_pool
    assert not store.exists("c1")
    assert risk_score(env.payload, int(TrustLevel.LOCAL), model) >= model.quarantine_threshold


def test_taint_caps_trust_at_local(frozen_src: Path) -> None:
    _, gateway, _, _, _, gate = make_gate(frozen_src)
    env = gateway.issue(
        payload={"content": {}},
        producer_id="c1", producer_kind="child", parent_contract_id="ct",
        trust=TrustLevel.TRUSTED,  # 生产者声称最高
    )
    admission = gate.admit(env, record_id="c1", parent_trust=int(TrustLevel.LOCAL))
    assert admission.record.trust == int(TrustLevel.LOCAL)


def test_speculative_link_raises_risk(frozen_src: Path) -> None:
    _, _gateway, _, model, _, _gate = make_gate(frozen_src)
    base = risk_score({"content": {"edges": [], "speculative_links": 0}}, 0, model)
    spec = risk_score({"content": {"edges": [], "speculative_links": 1}}, 0, model)
    assert spec > base


def _record(rid: str, trust: int, edges=(), risk=0.0, **kw) -> MemoryRecord:
    return MemoryRecord(
        record_id=rid,
        payload={},
        trust=trust,
        risk=risk,
        provenance=None,
        edges=list(edges),
        **kw,
    )


def test_selection_integrity_blocks_dangling_edge(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    store = MemoryStore()
    store.add(_record("a", int(TrustLevel.VALIDATED), edges=["missing"]))
    gate = RetrievalGate(model, store)
    result = gate.retrieve(["a"])
    assert result.records == []
    assert any("不存在的条目" in v for v in result.violations)


def test_selection_integrity_blocks_tainted_edge(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    store = MemoryStore()
    store.add(_record("low", int(TrustLevel.QUARANTINED)))
    store.add(_record("high", int(TrustLevel.VALIDATED), edges=["low"]))
    gate = RetrievalGate(model, store)
    result = gate.retrieve(["high"])
    assert result.records == []
    assert any("低信任条目" in v for v in result.violations)


def test_selection_integrity_blocks_unrechecked_speculative_edge(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    store = MemoryStore()
    store.add(_record("spec", int(TrustLevel.LOCAL), speculative=True, rechecks=0))
    store.add(_record("a", int(TrustLevel.LOCAL), edges=["spec"]))
    gate = RetrievalGate(model, store)
    result = gate.retrieve(["a"])
    assert result.records == []


def test_high_risk_entry_passes_when_ablation_clears(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    store = MemoryStore()
    store.add(_record("risky", int(TrustLevel.LOCAL), risk=0.9))
    gate = RetrievalGate(model, store, ablation_probe=lambda r: False, seed=1)
    result = gate.retrieve(["risky"])
    assert [r.record_id for r in result.records] == ["risky"]


def test_high_risk_entry_blocked_by_ablation_majority(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    store = MemoryStore()
    store.add(_record("risky", int(TrustLevel.LOCAL), risk=0.9))
    gate = RetrievalGate(model, store, ablation_probe=lambda r: True, seed=1)
    result = gate.retrieve(["risky"])
    assert result.records == []
    assert result.false_block == 1


def test_promotion_requires_evidence_for_speculative(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    rec = _record(
        "s", int(TrustLevel.LOCAL), speculative=True,
        references=0, acceptances=0, rechecks=0,
    )
    assert not promotion_decision(rec, model).allowed
    rec2 = _record(
        "s2", int(TrustLevel.LOCAL), speculative=True,
        references=model.promotion_min_references,
        acceptances=1,
        rechecks=model.promotion_min_rechecks,
    )
    assert promotion_decision(rec2, model).allowed


def test_quarantined_record_cannot_promote(frozen_src: Path) -> None:
    model = RiskModel.from_frozen(frozen_src)
    rec = _record("q", int(TrustLevel.QUARANTINED), quarantined=True)
    assert not promotion_decision(rec, model).allowed


def test_reuse_requires_confirmation_for_unverified_citation(frozen_src: Path) -> None:
    rec = _record("u", int(TrustLevel.LOCAL))
    decision = reuse_decision(rec, cited=True)
    assert not decision.auto_apply
    assert decision.requires_confirmation
    verified = _record("v", int(TrustLevel.VALIDATED))
    assert reuse_decision(verified, cited=True).auto_apply
    assert reuse_decision(rec, cited=False).auto_apply
