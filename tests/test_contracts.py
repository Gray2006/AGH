from __future__ import annotations

import json

import pytest
from jsonschema import Draft7Validator
from pydantic import ValidationError

from agh.contracts import (
    AbstractSignature,
    ChildSubmission,
    CoverageClaim,
    GestaltReconstruction,
    Skeleton,
    SkeletonMove,
    export_schemas,
    model_schema,
    reconstruction_schema,
)


def make_recon(**over: object) -> GestaltReconstruction:
    data = dict(
        child_id="c1",
        contract_id="ct1",
        skeleton_id="sk1",
        parts=["P1", "C1"],
        coverage=CoverageClaim(covered=["P1"]),
        signature=AbstractSignature(signature_id="s1", features=["a-b"]),
        self_confidence=0.5,
        content={"edges": [["P1", "C1"]]},
    )
    data.update(over)
    return GestaltReconstruction(**data)


def test_extra_field_forbidden_on_wire_models() -> None:
    with pytest.raises(ValidationError):
        ChildSubmission(
            submission_id="s",
            child_id="c1",
            contract_id="ct1",
            payload=make_recon(),
            produced_at_ms=0,
            trust=3,
        )


def test_child_cannot_declare_provenance() -> None:
    """D6：子级回传结构里根本没有 provenance 字段。"""
    with pytest.raises(ValidationError):
        make_recon(provenance={"trust": 3})


def test_schema_hardened_recursively() -> None:
    schema = model_schema(ChildSubmission)
    assert schema["additionalProperties"] is False
    payload_schema = schema["properties"]["payload"]
    if "$ref" in payload_schema:
        payload_schema = schema["$defs"][payload_schema["$ref"].split("/")[-1]]
    assert payload_schema["additionalProperties"] is False
    assert "trust" not in payload_schema["properties"]


def test_contract_schema_uses_contains_not_must_include() -> None:
    sk = Skeleton(
        skeleton_id="sk1",
        nodes=["M0", "P1", "C1"],
        edges=[("M0", "P1")],
        required_items=["P1", "C1"],
        moves=[SkeletonMove(node="P1", vertical=True, declared_depth=0.5, preserved_depth=0.5)],
    )
    schema = reconstruction_schema(sk)
    text = json.dumps(schema)
    assert "must_include" not in text
    assert "contains" in text
    Draft7Validator.check_schema(schema)


def test_contains_rejects_missing_required_item() -> None:
    sk = Skeleton(
        skeleton_id="sk1",
        nodes=["M0", "P1", "C1"],
        required_items=["P1", "C1"],
        moves=[SkeletonMove(node="P1", vertical=True, declared_depth=0.5, preserved_depth=0.5)],
        min_vertical_moves=0,
    )
    validator = Draft7Validator(reconstruction_schema(sk))
    good = make_recon(parts=["M0", "P1", "C1"], content={})
    errors = list(validator.iter_errors(good.model_dump(mode="json")))
    assert not errors, errors
    bad = make_recon(parts=["M0", "P1"], content={})
    errors = list(validator.iter_errors(bad.model_dump(mode="json")))
    assert errors


def test_naming_unified_and_schema_versioned(tmp_path) -> None:
    schema = model_schema(GestaltReconstruction)
    assert "parent_contract_id" not in schema["properties"]  # 只在 Contract/Provenance 上
    written = export_schemas(tmp_path)
    raw = json.loads(written["child_submission"].read_text(encoding="utf-8"))
    assert raw["$schema"].endswith("draft-07/schema#")


def test_skeleton_rejects_edge_to_unknown_node() -> None:
    with pytest.raises(ValidationError):
        Skeleton(skeleton_id="sk", nodes=["A"], edges=[("A", "B")])


def test_skeleton_rejects_self_loop() -> None:
    with pytest.raises(ValidationError):
        Skeleton(skeleton_id="sk", nodes=["A"], edges=[("A", "A")])
