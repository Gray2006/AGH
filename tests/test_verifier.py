from __future__ import annotations

import pytest

from agh.contracts import (
    AbstractSignature,
    CoverageClaim,
    GestaltReconstruction,
    Skeleton,
    SkeletonMove,
)
from agh.verifier import CoverageVerifier, StructuralVerifier, make_verifier


def skeleton() -> Skeleton:
    return Skeleton(
        skeleton_id="sk-v",
        nodes=["M0", "P1", "C1"],
        edges=[("M0", "P1"), ("P1", "C1")],
        required_items=["P1", "C1"],
        moves=[
            SkeletonMove(node="P1", vertical=True, declared_depth=0.5, preserved_depth=0.5),
            SkeletonMove(node="C1", vertical=True, declared_depth=0.8, preserved_depth=0.8),
        ],
        min_vertical_moves=1,
    )


def recon(parts, edges, features=()) -> GestaltReconstruction:
    return GestaltReconstruction(
        child_id="c",
        contract_id="ct",
        skeleton_id="sk-v",
        parts=list(parts),
        coverage=CoverageClaim(covered=[p for p in parts if p in {"P1", "C1"}]),
        signature=AbstractSignature(signature_id="s", features=list(features)),
        self_confidence=0.5,
        content={"edges": [list(e) for e in edges]},
    )


def test_structural_verifier_requires_parts_and_edges() -> None:
    v = StructuralVerifier()
    full = recon(["M0", "P1", "C1"], [("M0", "P1"), ("P1", "C1")])
    assert v.score(full, skeleton()) == pytest.approx(1.0)
    no_edges = recon(["M0", "P1", "C1"], [])
    assert v.score(no_edges, skeleton()) == pytest.approx(0.0)
    missing_part = recon(["M0", "P1"], [("M0", "P1"), ("P1", "C1")])
    assert v.score(missing_part, skeleton()) == pytest.approx(0.5)


def test_structural_verifier_accepts_edge_features() -> None:
    v = StructuralVerifier()
    cand = recon(["M0", "P1", "C1"], [], features=["M0-P1", "P1-C1"])
    assert v.score(cand, skeleton()) == pytest.approx(1.0)


def test_structural_verifier_ignores_self_reported_depths() -> None:
    v = StructuralVerifier()
    cand = recon(["M0", "P1", "C1"], [("M0", "P1"), ("P1", "C1")])
    cand = cand.model_copy(update={"content": {**cand.content, "vertical_moves": ["P1", "C1"]}})
    assert v.score(cand, skeleton()) == pytest.approx(1.0)


def test_coverage_verifier() -> None:
    v = CoverageVerifier()
    assert v.score(recon(["P1"], []), skeleton()) == pytest.approx(0.5)
    assert v.score(recon(["P1", "C1"], []), skeleton()) == pytest.approx(1.0)


def test_make_verifier() -> None:
    assert make_verifier("structural").name == "structural"
    with pytest.raises(ValueError):
        make_verifier("nope")


def test_llm_judge_blind_prompt_has_no_rule() -> None:
    from agh.verifier import LlmJudgeVerifier

    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return '{"support": 0.5}'

    judge = LlmJudgeVerifier(complete=complete, blind=True)
    sk = skeleton()
    cand = recon(["M0", "P1", "C1"], [("M0", "P1"), ("P1", "C1")])
    assert judge.score(cand, sk) == pytest.approx(0.5)
    assert "规则：" not in prompts[0]
    assert "独立评审" in prompts[0]


def test_llm_judge_clamps_and_handles_garbage() -> None:
    from agh.verifier import LlmJudgeVerifier

    sk = skeleton()
    cand = recon(["M0"], [])
    assert LlmJudgeVerifier(complete=lambda _p: '{"support": 3}', blind=True).score(cand, sk) == 1.0
    assert LlmJudgeVerifier(complete=lambda _p: "garbage", blind=True).score(cand, sk) == 0.0


def test_known_answer_set() -> None:
    """已知答案集：正例覆盖全部垂直节点且有边，反例缺边或缺节点。

    这验证的是「实现符合它声明的那条规则」，不是「规则本身正确」。
    """
    from agh.verifier import StructuralVerifier

    v = StructuralVerifier()
    sk = skeleton()
    cases = [
        (["M0", "P1", "C1"], [("M0", "P1"), ("P1", "C1")], 1.0),
        (["M0", "P1", "C1"], [("M0", "P1")], 0.5),
        (["M0", "P1"], [("M0", "P1"), ("P1", "C1")], 0.5),
        (["M0"], [("M0", "P1"), ("P1", "C1")], 0.0),
        (["M0", "P1", "C1"], [], 0.0),
    ]
    for parts, edges, expected in cases:
        assert v.score(recon(parts, edges), sk) == pytest.approx(expected)
