"""可验证遗忘。

「删掉」在审计系统里不能只是从库里抹掉：得留下可核对的墓碑，并且能证明
被遗忘的内容没有残留在别处（记录正文、边、派生引用）。

- Tombstone：记录 id、内容哈希、时间、原因、签名；
- residual_scan：扫记录与边，找出仍引用被遗忘 id 的地方；
- verify_forgetting：墓碑签名 + 残留扫描一起给出结论。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .crypto import Key, canonical_bytes, sha256_hex, sign_with, verify_with


@dataclass(frozen=True)
class Tombstone:
    record_id: str
    erased_at_ms: int
    content_hash: str
    reason: str
    kid: str
    sig: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "erased_at_ms": self.erased_at_ms,
            "content_hash": self.content_hash,
            "reason": self.reason,
            "kid": self.kid,
            "sig": self.sig,
        }


def _tombstone_message(t: Tombstone) -> str:
    return "|".join([t.record_id, str(t.erased_at_ms), t.content_hash, t.reason, t.kid])


class ForgettingRegistry:
    def __init__(self, key: Key, clock: Callable[[], int] | None = None) -> None:
        self.key = key
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._tombstones: dict[str, Tombstone] = {}

    def forget(self, record_id: str, content: Any, reason: str = "") -> Tombstone:
        base = Tombstone(
            record_id=record_id,
            erased_at_ms=self._clock(),
            content_hash=sha256_hex(content),
            reason=reason,
            kid=self.key.kid,
            sig="",
        )
        tombstone = Tombstone(**{**base.as_dict(), "sig": sign_with(self.key, _tombstone_message(base))})
        self._tombstones[record_id] = tombstone
        return tombstone

    def is_forgotten(self, record_id: str) -> bool:
        return record_id in self._tombstones

    def verify(self, tombstone: Tombstone) -> bool:
        return verify_with(self.key, _tombstone_message(tombstone), tombstone.sig)

    def tombstones(self) -> list[Tombstone]:
        return list(self._tombstones.values())


def residual_scan(
    forgotten: Iterable[str],
    records: Iterable[dict[str, Any]],
    edges: Iterable[tuple[str, str]] = (),
) -> list[str]:
    """返回仍被引用的被遗忘 id（去重、排序）。"""
    targets = set(forgotten)
    hits: set[str] = set()
    for record in records:
        blob = canonical_bytes(record).decode("utf-8")
        for target in targets:
            if target in blob:
                hits.add(target)
    for a, b in edges:
        if a in targets:
            hits.add(a)
        if b in targets:
            hits.add(b)
    return sorted(hits)


def verify_forgetting(
    registry: ForgettingRegistry,
    records: Iterable[dict[str, Any]],
    edges: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    tombstones = registry.tombstones()
    bad = [t.record_id for t in tombstones if not registry.verify(t)]
    residuals = residual_scan([t.record_id for t in tombstones], records, edges)
    return {
        "ok": not bad and not residuals,
        "tombstones": len(tombstones),
        "bad_signatures": bad,
        "residuals": residuals,
    }


__all__ = ["ForgettingRegistry", "Tombstone", "residual_scan", "verify_forgetting"]
