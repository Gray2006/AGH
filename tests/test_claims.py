from __future__ import annotations

from agh.claims import (
    TransparencyLog,
    inclusion_proof,
    merkle_root,
    sign_statement,
    verify_inclusion,
    verify_statement,
)
from agh.crypto import KeyRing


def key():
    return KeyRing.with_secret("issuer-1", b"k" * 16).get("issuer-1")


def test_merkle_root_deterministic() -> None:
    assert merkle_root(["a", "b", "c"]) == merkle_root(["a", "b", "c"])
    assert merkle_root(["a", "b"]) != merkle_root(["a", "c"])


def test_inclusion_proof_for_every_leaf() -> None:
    leaves = ["a", "b", "c", "d", "e"]
    root = merkle_root(leaves)
    for index, leaf in enumerate(leaves):
        assert verify_inclusion(leaf, inclusion_proof(leaves, index), root)
    assert not verify_inclusion("z", inclusion_proof(leaves, 0), root)


def test_statement_sign_and_verify() -> None:
    statement = sign_statement(
        key(),
        statement_id="st-1",
        issuer="org-a",
        subject="model-x",
        claim="trained-on-licensed-data",
        payload={"dataset": "d1"},
        issued_at_ms=1000,
    )
    assert verify_statement(key(), statement)
    bad = type(statement)(**{**statement.as_dict(), "claim": "other"})
    assert not verify_statement(key(), bad)


def test_transparency_log_inclusion_and_head() -> None:
    log = TransparencyLog(key(), clock=lambda: 2000)
    statements = [
        sign_statement(
            key(),
            statement_id=f"st-{i}",
            issuer="org-a",
            subject="model-x",
            claim="c",
            payload={"i": i},
            issued_at_ms=1000 + i,
        )
        for i in range(4)
    ]
    for statement in statements:
        log.append(statement)
    assert log.size == 4
    for index, statement in enumerate(statements):
        assert log.verify_entry(statement, index)
    head = log.signed_head()
    assert log.verify_head(head)
    assert not log.verify_head({**head, "size": 99})
