from __future__ import annotations

import json

import pytest

from agh.contracts import Skeleton, SkeletonMove
from agh.llm import ChildOutputError, LlmChild, RuleChild, build_prompt, extract_json
from agh.pipeline import m0_skeleton


def skeleton() -> Skeleton:
    return Skeleton(
        skeleton_id="sk-llm",
        nodes=["M0", "P1", "C1", "C2"],
        edges=[("M0", "P1"), ("P1", "C1"), ("P1", "C2")],
        required_items=["P1", "C1", "C2"],
        moves=[SkeletonMove(node="P1", vertical=True, declared_depth=0.5, preserved_depth=0.5)],
        min_vertical_moves=1,
    )


def valid_payload(sk: Skeleton) -> dict:
    return {
        "child_id": "llm-child",
        "contract_id": "ct-llm",
        "skeleton_id": sk.skeleton_id,
        "parts": ["M0", "P1", "C1", "C2"],
        "coverage": {"covered": ["P1", "C1", "C2"]},
        "signature": {"signature_id": "s", "features": ["M0-P1", "P1-C1", "P1-C2"]},
        "self_confidence": 0.7,
        "content": {
            "edges": [["M0", "P1"], ["P1", "C1"], ["P1", "C2"]],
            "vertical_moves": [{"node": "P1", "declared_depth": 0.5, "preserved_depth": 0.5}],
        },
    }


def test_extract_json_handles_fence_and_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('先说明一下：{"a": {"b": 2}} 完事') == {"a": {"b": 2}}


def test_extract_json_rejects_garbage() -> None:
    with pytest.raises(ChildOutputError):
        extract_json("没有 JSON")


def test_prompt_carries_skeleton_not_answer() -> None:
    sk = skeleton()
    from agh.contracts import Contract

    contract = Contract(
        contract_id="ct-llm", parent_id="p", skeleton=sk, budget_max_tokens=1, ttl_ms=1
    )
    prompt = build_prompt(contract, ["M0-P1"])
    for token in ("P1", "C1", "C2", "必须覆盖", "M0-P1"):
        assert token in prompt
    assert "答案" not in prompt


def test_llm_child_accepts_valid_json() -> None:
    sk = skeleton()
    payload = json.dumps(valid_payload(sk))
    child = LlmChild(name="llm-child", complete=lambda _p: payload, skeleton=sk)
    recon = child.reconstruct("ct-llm")
    assert recon.child_id == "llm-child"
    assert set(recon.coverage.covered) == {"P1", "C1", "C2"}


def test_llm_child_rejects_missing_required_part() -> None:
    sk = skeleton()
    payload = valid_payload(sk)
    payload["parts"] = ["M0", "P1"]
    child = LlmChild(name="llm-child", complete=lambda _p: json.dumps(payload), skeleton=sk)
    with pytest.raises(ChildOutputError) as exc:
        child.reconstruct("ct-llm")
    assert "不符合契约" in str(exc.value)
    assert exc.value.errors


def test_llm_child_requires_vertical_moves() -> None:
    sk = skeleton()
    payload = valid_payload(sk)
    payload["content"].pop("vertical_moves")
    child = LlmChild(name="llm-child", complete=lambda _p: json.dumps(payload), skeleton=sk)
    with pytest.raises(ChildOutputError):
        child.reconstruct("ct-llm")


def test_rule_child_adapter() -> None:
    from agh.pipeline import faithful_child

    child = RuleChild(name="faithful", fn=faithful_child)
    recon = child.reconstruct("ct-1")
    assert recon.child_id == "child-faithful"


def test_m0_skeleton_is_valid_for_llm_prompt() -> None:
    sk = m0_skeleton()
    assert sk.min_vertical_moves >= 1


def test_prompt_includes_reference_when_given() -> None:
    from agh.contracts import Contract

    sk = skeleton()
    contract = Contract(
        contract_id="ct-llm", parent_id="p", skeleton=sk, budget_max_tokens=1, ttl_ms=1
    )
    reference = {"child_id": "ref", "parts": ["P1", "C1", "C2"]}
    prompt = build_prompt(contract, None, reference)
    assert "参考实现" in prompt
    assert '"child_id": "ref"' in prompt


def test_llm_child_passes_reference() -> None:
    sk = skeleton()
    payload = json.dumps(valid_payload(sk))
    seen: list[str] = []

    def complete(prompt: str) -> str:
        seen.append(prompt)
        return payload

    child = LlmChild(
        name="llm-child", complete=complete, skeleton=sk, reference={"child_id": "ref"}
    )
    child.reconstruct("ct-llm")
    assert "参考实现" in seen[0]


def test_prompt_includes_structural_hints() -> None:
    from agh.contracts import Contract

    sk = skeleton()
    contract = Contract(
        contract_id="ct-llm", parent_id="p", skeleton=sk, budget_max_tokens=1, ttl_ms=1
    )
    prompt = build_prompt(contract, None, None, True)
    assert "特征命名约定" in prompt
    assert "pred:hierarchical" in prompt
    plain = build_prompt(contract)
    assert "特征命名约定" not in plain
