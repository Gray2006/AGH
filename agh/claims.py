"""跨组织声明与透明日志（SCITT 方向的最小实现）。

- Statement：签发方对某主体的一条声明，带 payload 哈希与签名；
- TransparencyLog：Merkle 树，append 后给出包含证明，树头可签名；
- 验证：声明签名 + 包含证明 + 树头签名，三方对上才算成立。

不实现 SCITT 的 CBOR/COSE 编码，也不做跨日志一致性证明；接口留在这里，
需要时把编码层换掉即可。
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .crypto import Key, canonical_bytes, sha256_hex, sign_with, verify_with


def _leaf_hash(value: str) -> str:
    return hashlib.sha256(("leaf:" + value).encode("utf-8")).hexdigest()


def _node_hash(left: str, right: str) -> str:
    return hashlib.sha256(("node:" + left + right).encode("utf-8")).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return hashlib.sha256(b"empty").hexdigest()
    level = [_leaf_hash(x) for x in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [_node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def inclusion_proof(leaves: list[str], index: int) -> list[dict[str, str]]:
    if not 0 <= index < len(leaves):
        raise IndexError("index 越界")
    level = [_leaf_hash(x) for x in leaves]
    idx = index
    proof: list[dict[str, str]] = []
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling = idx ^ 1
        proof.append({"side": "left" if sibling < idx else "right", "hash": level[sibling]})
        level = [_node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_inclusion(leaf: str, proof: list[dict[str, str]], root: str) -> bool:
    current = _leaf_hash(leaf)
    for step in proof:
        current = (
            _node_hash(step["hash"], current)
            if step["side"] == "left"
            else _node_hash(current, step["hash"])
        )
    return current == root


@dataclass(frozen=True)
class Statement:
    statement_id: str
    issuer: str
    subject: str
    claim: str
    payload_sha256: str
    issued_at_ms: int
    kid: str
    sig: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement_id": self.statement_id,
            "issuer": self.issuer,
            "subject": self.subject,
            "claim": self.claim,
            "payload_sha256": self.payload_sha256,
            "issued_at_ms": self.issued_at_ms,
            "kid": self.kid,
            "sig": self.sig,
        }


def _statement_message(s: Statement) -> str:
    return "|".join(
        [s.statement_id, s.issuer, s.subject, s.claim, s.payload_sha256, str(s.issued_at_ms), s.kid]
    )


def sign_statement(
    key: Key,
    *,
    statement_id: str,
    issuer: str,
    subject: str,
    claim: str,
    payload: Any,
    issued_at_ms: int | None = None,
) -> Statement:
    base = Statement(
        statement_id=statement_id,
        issuer=issuer,
        subject=subject,
        claim=claim,
        payload_sha256=sha256_hex(payload),
        issued_at_ms=issued_at_ms if issued_at_ms is not None else int(time.time() * 1000),
        kid=key.kid,
        sig="",
    )
    return Statement(**{**base.as_dict(), "sig": sign_with(key, _statement_message(base))})


def verify_statement(key: Key, statement: Statement) -> bool:
    return verify_with(key, _statement_message(statement), statement.sig)


class TransparencyLog:
    """只追加的 Merkle 日志；树头可签名。"""

    def __init__(self, key: Key, clock: Callable[[], int] | None = None) -> None:
        self.key = key
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._leaves: list[str] = []

    @property
    def size(self) -> int:
        return len(self._leaves)

    def append(self, statement: Statement) -> int:
        self._leaves.append(canonical_bytes(statement.as_dict()).decode("utf-8"))
        return len(self._leaves) - 1

    def root(self) -> str:
        return merkle_root(self._leaves)

    def prove(self, index: int) -> list[dict[str, str]]:
        return inclusion_proof(self._leaves, index)

    def verify_entry(self, statement: Statement, index: int) -> bool:
        leaf = canonical_bytes(statement.as_dict()).decode("utf-8")
        return verify_inclusion(leaf, self.prove(index), self.root())

    def signed_head(self) -> dict[str, Any]:
        head = {"root": self.root(), "size": self.size, "issued_at_ms": self._clock()}
        message = f"{head['root']}|{head['size']}|{head['issued_at_ms']}"
        head["kid"] = self.key.kid
        head["sig"] = sign_with(self.key, message)
        return head

    def verify_head(self, head: dict[str, Any]) -> bool:
        message = f"{head['root']}|{head['size']}|{head['issued_at_ms']}"
        return verify_with(self.key, message, str(head.get("sig", "")))


__all__ = [
    "Statement",
    "TransparencyLog",
    "inclusion_proof",
    "merkle_root",
    "sign_statement",
    "verify_inclusion",
    "verify_statement",
]
