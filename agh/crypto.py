"""签名与来源（D1 / D12）。

要点：
- provenance 只能由网关签发，子级提交包里根本没有这个字段（contracts 已 forbid）。
- 验签失败、哈希不符、nonce 重放、序号回退，一律拒收，不做「警告后放行」。
- 密钥有 kid、轮换时间、吊销名单；吊销立即生效。
- 结算消息带 nonce + epoch + 单调 seq + 裁判版本哈希，防跨版本重放。

限制（写进文档，不藏）：M0 用 HMAC-SHA256 共享密钥，等价于「网关与服务端同机」。
生产形态应换成 Ed25519：网关持私钥，验方只持公钥，共享密钥一旦泄露整条链路失效。
接口保持不变，换实现只动 KeyRing/Signer。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    SCHEMA_VERSION,
    Provenance,
    SettlementMessage,
    SignedEnvelope,
    TrustLevel,
)


class ProvenanceError(Exception):
    """来源校验失败。code 用于计数指标（签名验证失败数 / 重放数）。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _sign(secret: bytes, message: str) -> str:
    return hmac.new(secret, message.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class Key:
    kid: str
    secret: bytes
    not_after_ms: int | None = None
    revoked: bool = False


class KeyRing:
    """简单密钥环：注册、轮换、吊销。"""

    def __init__(self) -> None:
        self._keys: dict[str, Key] = {}

    def register(self, kid: str, secret: bytes, not_after_ms: int | None = None) -> None:
        if kid in self._keys:
            raise ValueError(f"kid 已存在: {kid}")
        self._keys[kid] = Key(kid=kid, secret=secret, not_after_ms=not_after_ms)

    def get(self, kid: str) -> Key:
        key = self._keys.get(kid)
        if key is None:
            raise ProvenanceError("unknown_kid", kid)
        if key.revoked:
            raise ProvenanceError("revoked_kid", kid)
        return key

    def revoke(self, kid: str) -> None:
        self.get(kid).revoked = True

    @classmethod
    def with_secret(cls, kid: str, secret: bytes) -> KeyRing:
        ring = cls()
        ring.register(kid, secret)
        return ring


def _provenance_message(p: Provenance) -> str:
    return "|".join(
        [
            p.kid,
            p.event_id,
            p.producer_id,
            p.producer_kind,
            p.parent_contract_id or "-",
            str(int(p.trust)),
            str(p.issued_at_ms),
            str(p.seq),
            p.nonce,
            p.payload_sha256,
        ]
    )


class ProvenanceGateway:
    """网关：唯一有 provenance 写权限的组件。"""

    def __init__(
        self,
        keyring: KeyRing,
        kid: str,
        clock: Callable[[], int] | None = None,
        nonce_source: Callable[[], str] | None = None,
    ) -> None:
        self.keyring = keyring
        self.kid = kid
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._nonce = nonce_source or (lambda: secrets.token_hex(8))
        self._seq: dict[str, int] = {}

    def issue(
        self,
        *,
        payload: dict[str, Any],
        producer_id: str,
        producer_kind: str,
        parent_contract_id: str | None,
        trust: int | TrustLevel,
        event_id: str | None = None,
    ) -> SignedEnvelope:
        payload_hash = sha256_hex(payload)
        seq = self._seq.get(producer_id, 0)
        self._seq[producer_id] = seq + 1
        prov = Provenance(
            event_id=event_id or f"evt-{secrets.token_hex(6)}",
            producer_id=producer_id,
            producer_kind=producer_kind,  # type: ignore[arg-type]
            parent_contract_id=parent_contract_id,
            trust=int(trust),
            issued_at_ms=self._clock(),
            seq=seq,
            nonce=self._nonce(),
            kid=self.kid,
            payload_sha256=payload_hash,
            sig="0" * 64,
        )
        sig = _sign(self.keyring.get(self.kid).secret, _provenance_message(prov))
        prov = prov.model_copy(update={"sig": sig})
        return SignedEnvelope(provenance=prov, payload=payload)


@dataclass
class VerificationStats:
    """指标：签名验证失败数、重放拦截数（§4 新增指标）。"""

    verified: int = 0
    failures: dict[str, int] = field(default_factory=dict)

    def fail(self, code: str) -> None:
        self.failures[code] = self.failures.get(code, 0) + 1

    @property
    def failure_count(self) -> int:
        return sum(self.failures.values())


class EnvelopeVerifier:
    """验签 + 防重放。"""

    def __init__(
        self,
        keyring: KeyRing,
        clock: Callable[[], int] | None = None,
        max_skew_ms: int = 60_000,
        stats: VerificationStats | None = None,
    ) -> None:
        self.keyring = keyring
        self._clock = clock or (lambda: int(time.time() * 1000))
        self.max_skew_ms = max_skew_ms
        self.stats = stats or VerificationStats()
        self._last_seq: dict[str, int] = {}
        self._nonces: set[str] = set()

    def verify(self, envelope: SignedEnvelope) -> Provenance:
        try:
            return self._verify(envelope)
        except ProvenanceError as exc:
            self.stats.fail(exc.code)
            raise

    def _verify(self, envelope: SignedEnvelope) -> Provenance:
        if envelope.schema_version != SCHEMA_VERSION:
            raise ProvenanceError("schema_version", envelope.schema_version)
        p = envelope.provenance
        if sha256_hex(envelope.payload) != p.payload_sha256:
            raise ProvenanceError("payload_hash_mismatch", p.event_id)
        key = self.keyring.get(p.kid)  # 未知/吊销在这里抛
        now = self._clock()
        if key.not_after_ms is not None and now > key.not_after_ms:
            raise ProvenanceError("expired_kid", p.kid)
        if abs(now - p.issued_at_ms) > self.max_skew_ms:
            raise ProvenanceError("clock_skew", str(p.issued_at_ms))
        expected = _sign(key.secret, _provenance_message(p))
        if not hmac.compare_digest(expected, p.sig):
            raise ProvenanceError("bad_sig", p.event_id)
        if p.nonce in self._nonces:
            raise ProvenanceError("replay_nonce", p.nonce)
        last = self._last_seq.get(p.producer_id)
        if last is not None and p.seq <= last:
            raise ProvenanceError("stale_seq", f"{p.producer_id}:{p.seq}<={last}")
        # 校验通过后才落状态，避免失败请求污染重放窗口
        self._nonces.add(p.nonce)
        self._last_seq[p.producer_id] = p.seq
        self.stats.verified += 1
        return p


def derive_trust(inputs: Iterable[int | TrustLevel]) -> TrustLevel:
    """污点传播：派生内容继承输入中最低信任等级，加工不能让信任升高（§3.1）。"""
    levels = [TrustLevel(int(x)) for x in inputs]
    if not levels:
        return TrustLevel.QUARANTINED
    return min(levels)


# --------------------------------------------------------------------------
# 结算（D12）
# --------------------------------------------------------------------------


def settlement_message(s: SettlementMessage) -> str:
    return "|".join(
        [
            s.kid,
            s.settlement_id,
            str(s.epoch),
            str(s.seq),
            s.nonce,
            s.judge_version_hash,
            f"{s.amount_usd:.6f}",
        ]
    )


def sign_settlement(
    *,
    keyring: KeyRing,
    kid: str,
    settlement_id: str,
    epoch: int,
    seq: int,
    judge_version_hash: str,
    amount_usd: float,
    nonce: str | None = None,
) -> SettlementMessage:
    msg = SettlementMessage(
        settlement_id=settlement_id,
        epoch=epoch,
        seq=seq,
        nonce=nonce or secrets.token_hex(8),
        judge_version_hash=judge_version_hash,
        amount_usd=amount_usd,
        kid=kid,
        sig="0" * 64,
    )
    sig = _sign(keyring.get(kid).secret, settlement_message(msg))
    return msg.model_copy(update={"sig": sig})


class SettlementVerifier:
    """结算验签：防重放 + 防跨版本重放 + 防序号回退。"""

    def __init__(self, keyring: KeyRing, expected_judge_hash: str) -> None:
        self.keyring = keyring
        self.expected_judge_hash = expected_judge_hash
        self._nonces: set[str] = set()
        self._last: dict[str, tuple[int, int]] = {}

    def verify(self, msg: SettlementMessage) -> None:
        key = self.keyring.get(msg.kid)
        if not hmac.compare_digest(
            _sign(key.secret, settlement_message(msg)), msg.sig
        ):
            raise ProvenanceError("bad_settlement_sig", msg.settlement_id)
        if msg.judge_version_hash != self.expected_judge_hash:
            raise ProvenanceError("judge_version_mismatch", msg.settlement_id)
        if msg.nonce in self._nonces:
            raise ProvenanceError("replay_nonce", msg.nonce)
        last = self._last.get(msg.settlement_id)
        if last is not None and (
            msg.epoch < last[0] or (msg.epoch == last[0] and msg.seq <= last[1])
        ):
            raise ProvenanceError("stale_seq", msg.settlement_id)
        self._nonces.add(msg.nonce)
        self._last[msg.settlement_id] = (msg.epoch, msg.seq)


def keyring_from_mapping(keys: Mapping[str, bytes]) -> KeyRing:
    ring = KeyRing()
    for kid, secret in keys.items():
        ring.register(kid, secret)
    return ring
