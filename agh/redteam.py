"""红队演练：按攻击者视角逐条验证防线，全部本地、不联网。

覆盖：伪造出处、篡改载荷、重放、序号回退、日志截断、冻结层篡改、结算重放。
输出是「攻击 → 是否被拦住 → 拦截码」，任何一条没拦住都算失败。
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import SignedEnvelope, TrustLevel
from .crypto import (
    EnvelopeVerifier,
    KeyRing,
    ProvenanceError,
    ProvenanceGateway,
    SettlementVerifier,
    sign_settlement,
)
from .eventlog import EventLog, LogTampered
from .frozen import FrozenLayer, FrozenLayerTampered
from .pipeline import DEV_KID, DEV_SECRET


@dataclass
class AttackResult:
    name: str
    defended: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"attack": self.name, "defended": self.defended, "detail": self.detail}


def _gateway() -> tuple[KeyRing, ProvenanceGateway]:
    ring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    return ring, ProvenanceGateway(ring, DEV_KID)


def _issue(gw: ProvenanceGateway) -> SignedEnvelope:
    return gw.issue(
        payload={"a": 1},
        producer_id="attacker",
        producer_kind="child",
        parent_contract_id=None,
        trust=TrustLevel.LOCAL,
    )


def run_attacks(frozen_root: Path) -> list[AttackResult]:
    results: list[AttackResult] = []
    ring, gw = _gateway()

    # 1) 伪造签名
    env = _issue(gw)
    raw = env.model_dump(mode="json")
    raw["provenance"]["sig"] = "0" * len(raw["provenance"]["sig"])
    try:
        EnvelopeVerifier(ring).verify(SignedEnvelope.model_validate(raw))
        results.append(AttackResult("forged_signature", False))
    except ProvenanceError as exc:
        results.append(AttackResult("forged_signature", True, exc.code))

    # 2) 篡改载荷
    raw = _issue(gw).model_dump(mode="json")
    raw["payload"]["a"] = 999
    try:
        EnvelopeVerifier(ring).verify(SignedEnvelope.model_validate(raw))
        results.append(AttackResult("tampered_payload", False))
    except ProvenanceError as exc:
        results.append(AttackResult("tampered_payload", True, exc.code))

    # 3) 重放
    verifier = EnvelopeVerifier(ring)
    env = _issue(gw)
    verifier.verify(env)
    try:
        verifier.verify(env)
        results.append(AttackResult("replay_nonce", False))
    except ProvenanceError as exc:
        results.append(AttackResult("replay_nonce", True, exc.code))

    # 4) 序号回退
    gw2 = ProvenanceGateway(ring, DEV_KID)
    first = gw2.issue(
        payload={"a": 1}, producer_id="p", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    second = gw2.issue(
        payload={"a": 2}, producer_id="p", producer_kind="child",
        parent_contract_id=None, trust=TrustLevel.LOCAL,
    )
    v2 = EnvelopeVerifier(ring)
    v2.verify(second)
    try:
        v2.verify(first)
        results.append(AttackResult("stale_seq", False))
    except ProvenanceError as exc:
        results.append(AttackResult("stale_seq", True, exc.code))

    # 5) 日志截断：本地哈希链看不出来，必须靠外部记录的长度与链头
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        log = EventLog(path)
        for index in range(3):
            log.append("t", {"i": index})
        expected_head, expected_size = log.head(), log.size()
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        truncated = EventLog(path)
        try:
            truncated.verify()
            local_detected = False
        except LogTampered:
            local_detected = True
        try:
            truncated.verify_against(expected_head, expected_size)
            anchored_detected = False
        except LogTampered as exc:
            anchored_detected = True
            anchor_detail = str(exc)[:60]
        results.append(
            AttackResult(
                "log_truncation",
                anchored_detected,
                ("本地链未发现；" if not local_detected else "")
                + (anchor_detail if anchored_detected else "锚点也未发现"),
            )
        )

    # 6) 冻结层篡改
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "frozen"
        root.mkdir()
        (root / "x.json").write_text(json.dumps({"v": 1}), encoding="utf-8")
        layer = FrozenLayer(root)
        anchor = Path(tmp) / "anchor.json"
        layer.write_anchor(anchor, ring, DEV_KID)
        (root / "x.json").write_text(json.dumps({"v": 2}), encoding="utf-8")
        try:
            layer.verify(anchor, ring)
            results.append(AttackResult("frozen_tamper", False))
        except FrozenLayerTampered as exc:
            results.append(AttackResult("frozen_tamper", True, json.dumps(exc.diffs, ensure_ascii=False)[:80]))

    # 7) 结算重放
    msg = sign_settlement(
        keyring=ring, kid=DEV_KID, settlement_id="s1", epoch=1, seq=1,
        judge_version_hash="a" * 64, amount_usd=0.1,
    )
    sv = SettlementVerifier(ring, "a" * 64)
    sv.verify(msg)
    try:
        sv.verify(msg)
        results.append(AttackResult("settlement_replay", False))
    except ProvenanceError as exc:
        results.append(AttackResult("settlement_replay", True, exc.code))

    return results


def report(results: list[AttackResult]) -> dict[str, Any]:
    total = len(results)
    defended = sum(1 for r in results if r.defended)
    return {
        "total": total,
        "defended": defended,
        "all_defended": defended == total,
        "results": [r.as_dict() for r in results],
    }


__all__ = ["AttackResult", "report", "run_attacks"]
