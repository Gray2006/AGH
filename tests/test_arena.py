from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agh.arena import (
    ArenaConfig,
    Calibration,
    CompetitiveCandidate,
    InvalidSkeleton,
    arbitrate,
    dissent_causal_influence,
    diversity_precheck,
    evaluate_dissent,
    hard_filter,
    score_candidate,
    skeleton_violations,
    structural_distance,
    vertical_consistency,
)
from agh.contracts import (
    AbstractSignature as ContractSignature,
)
from agh.contracts import (
    CoverageClaim,
    GestaltReconstruction,
    Skeleton,
    SkeletonMove,
)


@pytest.fixture()
def cfg(frozen_src: Path) -> ArenaConfig:
    config = ArenaConfig.from_frozen(frozen_src)
    config.verify_weight_sum()
    return config


def skeleton(vertical: bool = True) -> Skeleton:
    moves = (
        [
            SkeletonMove(node="P1", vertical=True, declared_depth=0.5, preserved_depth=0.5),
            SkeletonMove(node="C1", vertical=True, declared_depth=1.0, preserved_depth=0.8),
        ]
        if vertical
        else [SkeletonMove(node="C1", vertical=False)]
    )
    return Skeleton(
        skeleton_id="sk",
        nodes=["M0", "P1", "C1", "C2"],
        edges=[("M0", "P1"), ("P1", "C1"), ("P1", "C2")],
        required_items=["P1", "C1"],
        moves=moves,
        min_vertical_moves=1 if vertical else 0,
    )


PARENT = ContractSignature(signature_id="p", features=["M0-P1", "P1-C1", "P1-C2"])


def recon(features=None, covered=None, parts=None, confidence=0.8, child_id="c1"):
    return GestaltReconstruction(
        child_id=child_id,
        contract_id="ct",
        skeleton_id="sk",
        parts=parts or ["M0", "P1", "C1", "C2"],
        coverage=CoverageClaim(covered=covered or ["P1", "C1"]),
        signature=ContractSignature(
            signature_id="s", features=features or ["M0-P1", "P1-C1", "P1-C2"]
        ),
        self_confidence=confidence,
        content={
            "edges": [["M0", "P1"], ["P1", "C1"], ["P1", "C2"]],
            "changed_nodes": [],
        },
    )


def test_vertical_consistency_zero_when_no_vertical_moves() -> None:
    vc, n = vertical_consistency(skeleton(vertical=False))
    assert (vc, n) == (0.0, 0)


def test_vertical_consistency_normal_when_vertical() -> None:
    vc, n = vertical_consistency(skeleton())
    assert n == 2
    assert vc == pytest.approx(0.9)


def test_horizontal_only_candidate_does_not_get_free_points(cfg: ArenaConfig) -> None:
    score = score_candidate(
        recon(), skeleton(vertical=False), cfg, verifier_score=0.8, parent_signature=PARENT
    )
    assert score.vertical_consistency == 0.0
    assert "无垂直移动" in "".join(score.notes)


def test_empty_required_items_is_invalid_skeleton(cfg: ArenaConfig) -> None:
    bad = Skeleton(
        skeleton_id="bad",
        nodes=["A"],
        required_items=[],
        moves=[SkeletonMove(node="A", vertical=True)],
    )
    cfg2 = ArenaConfig(
        weights=cfg.weights,
        dissent_tau=cfg.dissent_tau,
        dissent_score_floor=cfg.dissent_score_floor,
        top_k=cfg.top_k,
        diversity_min_pairwise=cfg.diversity_min_pairwise,
        diversity_min_clusters=cfg.diversity_min_clusters,
        oversample_factor=cfg.oversample_factor,
        min_vertical_moves=cfg.min_vertical_moves,
        calibration=cfg.calibration,
    )
    with pytest.raises(InvalidSkeleton):
        score_candidate(recon(), bad, cfg2)
    problems = skeleton_violations(bad, cfg)
    assert any("required_items" in p for p in problems)


def test_skeleton_violation_missing_vertical(cfg: ArenaConfig) -> None:
    problems = skeleton_violations(skeleton(vertical=False), cfg)
    assert any("垂直移动" in p for p in problems)


def test_hard_filter_catches_missing_required(cfg: ArenaConfig) -> None:
    filt = hard_filter(recon(parts=["M0", "P1"]), skeleton())
    assert not filt.passed
    assert any("缺必需项" in r for r in filt.reasons)


def test_confidence_requires_verifier_signal(cfg: ArenaConfig) -> None:
    score = score_candidate(recon(), skeleton(), cfg, verifier_score=None, parent_signature=PARENT)
    assert score.confidence == 0.0
    assert score.unverified
    with_signal = score_candidate(
        recon(), skeleton(), cfg, verifier_score=0.8, parent_signature=PARENT
    )
    assert with_signal.confidence == pytest.approx(
        0.75 * 0.8 + 0.25 * cfg.calibration.lookup(0.8)
    )


def test_calibration_lookup_bins() -> None:
    cal = Calibration(bins=((0.0, 0.5, 0.2), (0.5, 1.01, 0.9)), verifier_weight=0.5, self_report_weight=0.5)
    assert cal.lookup(0.1) == 0.2
    assert cal.lookup(0.99) == 0.9


def test_structural_distance_bounds() -> None:
    assert structural_distance({"a"}, {"a"}) == 0.0
    assert structural_distance({"a"}, {"b"}) == 1.0
    assert structural_distance(set(), set()) == 0.0


def test_dissent_admitted_for_dissimilar_candidate(cfg: ArenaConfig) -> None:
    cand = recon(features=["X-Y", "alt:flat"], child_id="cd")
    breakdown = score_candidate(cand, skeleton(), cfg, verifier_score=0.7, parent_signature=PARENT)
    decision = evaluate_dissent(
        cand, breakdown, pool=[PARENT.features], abstractions=[PARENT.features], cfg=cfg
    )
    assert decision.admitted
    assert decision.novelty > cfg.dissent_tau


def test_dissent_rejected_for_novelty_below_tau(cfg: ArenaConfig) -> None:
    cand = recon(features=["M0-P1", "P1-C1", "P1-C2"], child_id="cn")
    breakdown = score_candidate(cand, skeleton(), cfg, verifier_score=0.8, parent_signature=PARENT)
    decision = evaluate_dissent(cand, breakdown, pool=[PARENT.features], abstractions=[], cfg=cfg)
    assert not decision.admitted
    assert decision.reason == "novelty_below_tau"


def test_dissent_rejected_for_low_score(cfg: ArenaConfig) -> None:
    cand = GestaltReconstruction(
        child_id="cl",
        contract_id="ct",
        skeleton_id="sk",
        parts=["M0", "P1", "C1", "C2"],
        coverage=CoverageClaim(covered=[]),
        signature=ContractSignature(signature_id="s", features=["X-Y"]),
        self_confidence=0.0,
        content={"edges": [], "changed_nodes": ["M0", "P1", "C1", "C2"]},
    )
    strict = replace(cfg, dissent_score_floor=0.5)
    low = score_candidate(cand, skeleton(), strict, verifier_score=0.0, parent_signature=PARENT)
    assert low.score < strict.dissent_score_floor
    decision = evaluate_dissent(
        cand, low, pool=[PARENT.features], abstractions=[], cfg=strict
    )
    assert not decision.admitted
    assert decision.reason == "score_below_floor"


def test_diversity_precheck_flags_identical_candidates(cfg: ArenaConfig) -> None:
    same = [recon(child_id=f"c{i}") for i in range(3)]
    report = diversity_precheck(same, cfg)
    assert not report.sufficient
    assert report.requested_extra >= 1


def test_diversity_precheck_accepts_varied(cfg: ArenaConfig) -> None:
    varied = [
        recon(child_id="c1"),
        recon(features=["X-Y", "alt:flat"], child_id="c2"),
    ]
    report = diversity_precheck(varied, cfg)
    assert report.sufficient


def test_arbitration_is_deterministic(cfg: ArenaConfig) -> None:
    a = recon(child_id="a")
    b = recon(child_id="b", features=["X-Y", "alt"], confidence=0.4)
    candidates = [
        CompetitiveCandidate(a, score_candidate(a, skeleton(), cfg, verifier_score=0.9, parent_signature=PARENT)),
        CompetitiveCandidate(b, score_candidate(b, skeleton(), cfg, verifier_score=0.5, parent_signature=PARENT)),
    ]
    r1 = arbitrate(candidates, seed=7, cfg=cfg)
    r2 = arbitrate(candidates, seed=7, cfg=cfg)
    assert r1 == r2
    assert r1.winner == "a"


def test_arbitration_tie_break_uses_seed(cfg: ArenaConfig) -> None:
    a = recon(child_id="a")
    b = recon(child_id="b")
    breakdown = score_candidate(a, skeleton(), cfg, verifier_score=0.8, parent_signature=PARENT)
    candidates = [CompetitiveCandidate(a, breakdown), CompetitiveCandidate(b, breakdown)]
    results = {arbitrate(candidates, seed=s, cfg=cfg).winner for s in range(20)}
    assert len(results) == 2  # 种子确实改变并列时的胜者


def test_dissent_marks_contested_and_influence(cfg: ArenaConfig) -> None:
    a = recon(child_id="a")
    b = recon(features=["X-Y", "alt"], child_id="b")
    cand_a = CompetitiveCandidate(
        a, score_candidate(a, skeleton(), cfg, verifier_score=0.9, parent_signature=PARENT)
    )
    score_b = score_candidate(b, skeleton(), cfg, verifier_score=0.8, parent_signature=PARENT)
    decision = evaluate_dissent(
        b, score_b, pool=[a.signature.features], abstractions=[], cfg=cfg
    )
    assert decision.admitted
    cand_b = CompetitiveCandidate(
        b, score_b, dissent=decision
    )
    result = arbitrate([cand_a, cand_b], seed=7, cfg=cfg)
    assert result.contested
    assert result.winner == "a"
    influence = dissent_causal_influence([cand_a, cand_b], seed=7, cfg=cfg)
    assert influence["b"]["contested_removed"] is True


def test_vertical_consistency_uses_candidate_depths() -> None:
    from agh.arena import vertical_consistency

    sk = skeleton()
    moves = [
        {"node": m.node, "preserved_depth": m.declared_depth}
        for m in sk.moves
        if m.vertical
    ]
    good = recon().model_copy(update={"content": {"edges": [], "vertical_moves": moves}})
    good_vc, n = vertical_consistency(sk, good)
    assert n == 2
    assert good_vc == pytest.approx(1.0)
    missing = recon().model_copy(update={"content": {"edges": [], "vertical_moves": []}})
    missing_vc, _ = vertical_consistency(sk, missing)
    assert missing_vc < good_vc


def test_vertical_consistency_accepts_node_names() -> None:
    from agh.arena import vertical_consistency

    sk = skeleton()
    names = [m.node for m in sk.moves if m.vertical]
    cand = recon().model_copy(update={"content": {"edges": [], "vertical_moves": names}})
    vc, n = vertical_consistency(sk, cand)
    assert n == 2
    assert vc == pytest.approx(1.0)
