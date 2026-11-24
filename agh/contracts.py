"""契约层：唯一事实源（D6）。

规则：
1. JSON Schema 一律由 Pydantic 模型生成，不手写；手写 schema 就会漂移。
2. 所有模型 extra="forbid"，导出 schema 时递归补 additionalProperties: false。
3. 表达「必须覆盖某几项」用 draft-07 的 contains（D6 指出 must_include 不存在）。
4. 命名统一：dissent（不是 dissent_gestalt）、parent_contract_id（不是 parent_id）。
5. schema 带版本号，与包版本解耦。
"""

from __future__ import annotations

import copy
import json
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "agh-3.1"


class TrustLevel(IntEnum):
    """信任等级。数字越大越可信，污点传播取 min（D1 / §3.1）。"""

    QUARANTINED = 0
    LOCAL = 1
    VALIDATED = 2
    TRUSTED = 3


class _Wire(BaseModel):
    """线上契约基类：禁止额外字段，禁止运行期改写。"""

    model_config = ConfigDict(extra="forbid", frozen=True, ser_json_timedelta="float")


# --------------------------------------------------------------------------
# 结构骨架
# --------------------------------------------------------------------------


class SkeletonMove(_Wire):
    """一次骨架移动。

    垂直移动指沿层级上下移动（母体→父→子）；declared_depth / preserved_depth
    归一化到 [0,1]，供 vertical_consistency 计算（D3）。
    """

    node: str = Field(min_length=1)
    vertical: bool = False
    declared_depth: float = Field(default=0.0, ge=0.0, le=1.0)
    preserved_depth: float = Field(default=0.0, ge=0.0, le=1.0)


class Skeleton(_Wire):
    """被重构对象的骨架声明。"""

    skeleton_id: str = Field(min_length=1)
    nodes: list[str] = Field(min_length=1)
    edges: list[tuple[str, str]] = Field(default_factory=list)
    required_items: list[str] = Field(default_factory=list)
    moves: list[SkeletonMove] = Field(default_factory=list)
    min_vertical_moves: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def _edges_reference_known_nodes(self) -> Skeleton:
        known = set(self.nodes)
        for a, b in self.edges:
            if a not in known or b not in known:
                raise ValueError(f"边引用了不存在的节点: {a}-{b}")
            if a == b:
                raise ValueError(f"自环非法: {a}")
        return self

    @property
    def n_vertical(self) -> int:
        return sum(1 for m in self.moves if m.vertical)


class CoverageClaim(_Wire):
    """候选声明的覆盖情况。total_required=0 的 skeleton 视为非法（D3）。"""

    covered: list[str] = Field(default_factory=list)


class AbstractSignature(_Wire):
    """抽象签名：用于计算 dissent 的结构距离（D4）。

    features 是可解释的结构标签（节点/边/谓词名），不是自由文本。
    """

    signature_id: str = Field(min_length=1)
    features: list[str] = Field(default_factory=list)
    abstraction: bool = False


class GestaltReconstruction(_Wire):
    """子级回传的重构内容（payload）。注意：这里没有任何 provenance 字段。"""

    child_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    skeleton_id: str = Field(min_length=1)
    parts: list[str] = Field(min_length=1)
    coverage: CoverageClaim = Field(default_factory=CoverageClaim)
    signature: AbstractSignature
    # D5：自报置信只作为输入，绝不直接进评分
    self_confidence: float = Field(ge=0.0, le=1.0)
    content: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class Contract(_Wire):
    """父级下发的契约。"""

    contract_id: str = Field(min_length=1)
    parent_id: str = Field(min_length=1)  # 父级身份，与 parent_contract_id 区分
    skeleton: Skeleton
    budget_max_tokens: int = Field(gt=0)
    ttl_ms: int = Field(gt=0)
    frozen_refs: list[str] = Field(default_factory=list)


class ChildSubmission(_Wire):
    """子级提交包：子级能写到的最大范围。"""

    submission_id: str = Field(min_length=1)
    child_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    payload: GestaltReconstruction
    produced_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _ids_consistent(self) -> ChildSubmission:
        if self.payload.contract_id != self.contract_id:
            raise ValueError("payload.contract_id 与提交包 contract_id 不一致")
        if self.payload.child_id != self.child_id:
            raise ValueError("payload.child_id 与提交包 child_id 不一致")
        return self


# --------------------------------------------------------------------------
# provenance / 结算
# --------------------------------------------------------------------------


class Provenance(_Wire):
    """由网关签发的来源凭证（D1）。子级无写权限。"""

    event_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    producer_kind: Literal["mother", "parent", "child", "gateway"]
    parent_contract_id: str | None = None
    trust: int = Field(ge=int(TrustLevel.QUARANTINED), le=int(TrustLevel.TRUSTED))
    issued_at_ms: int = Field(ge=0)
    seq: int = Field(ge=0)
    nonce: str = Field(min_length=8)
    kid: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sig: str = Field(min_length=16)


class SignedEnvelope(_Wire):
    """网关签名信封：provenance + 不透明 payload。"""

    schema_version: str = SCHEMA_VERSION
    provenance: Provenance
    payload: dict[str, Any]


class SettlementMessage(_Wire):
    """结算消息（D12）：nonce + 单调序号 + 裁判版本哈希 + 密钥轮换。"""

    settlement_id: str = Field(min_length=1)
    epoch: int = Field(ge=0)
    seq: int = Field(ge=0)
    nonce: str = Field(min_length=8)
    judge_version_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    amount_usd: float = Field(ge=0.0)
    kid: str = Field(min_length=1)
    sig: str = Field(min_length=16)


# --------------------------------------------------------------------------
# 预算 / 账本
# --------------------------------------------------------------------------


class BudgetVector(_Wire):
    """D7：预算不是单一数值。"""

    compute_units: float = Field(default=0.0, ge=0.0)
    wall_ms: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0.0)

    def __add__(self, other: BudgetVector) -> BudgetVector:
        return BudgetVector(
            compute_units=self.compute_units + other.compute_units,
            wall_ms=self.wall_ms + other.wall_ms,
            usd=self.usd + other.usd,
        )

    def le(self, other: BudgetVector) -> bool:
        return (
            self.compute_units <= other.compute_units
            and self.wall_ms <= other.wall_ms
            and self.usd <= other.usd
        )


# --------------------------------------------------------------------------
# schema 导出
# --------------------------------------------------------------------------


def _harden(node: Any) -> Any:
    """递归补 additionalProperties: false（只对 object 类型）。"""
    if isinstance(node, list):
        return [_harden(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: _harden(v) for k, v in node.items()}
    if out.get("type") == "object" and "additionalProperties" not in out:
        out["additionalProperties"] = False
    return out


def model_schema(model: type[BaseModel]) -> dict[str, Any]:
    """生成硬化后的 JSON Schema。"""
    return _harden(model.model_json_schema(mode="validation"))  # type: ignore[arg-type]


def reconstruction_schema(skeleton: Skeleton) -> dict[str, Any]:
    """契约相关的重构 schema。

    D6：用 allOf + contains 表达「parts 必须包含骨架的每个 required_item」。
    """
    schema = model_schema(GestaltReconstruction)
    required = list(dict.fromkeys(skeleton.required_items))
    if required:
        schema["allOf"] = [
            {"properties": {"parts": {"contains": {"const": item}}}}
            for item in required
        ]
    if skeleton.min_vertical_moves > 0:
        schema.setdefault("allOf", []).append(
            {"properties": {"content": {"required": ["vertical_moves"]}}}
        )
    return schema


def export_schemas(out_dir: str | Path, skeleton: Skeleton | None = None) -> dict[str, Path]:
    """把 schema 落盘。契约由模型生成，不手写（§6 结构变更）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    models = {
        "child_submission": ChildSubmission,
        "gestalt_reconstruction": GestaltReconstruction,
        "skeleton": Skeleton,
        "contract": Contract,
        "signed_envelope": SignedEnvelope,
        "settlement_message": SettlementMessage,
        "budget_vector": BudgetVector,
    }
    for name, model in models.items():
        target = out / f"{name}.json"
        target.write_text(
            json.dumps(
                {"$schema": "http://json-schema.org/draft-07/schema#", **model_schema(model)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        written[name] = target
    if skeleton is not None:
        target = out / "gestalt_reconstruction.contract.json"
        target.write_text(
            json.dumps(
                {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    **reconstruction_schema(skeleton),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        written["gestalt_reconstruction.contract"] = target
    return written


def copy_skeleton(skeleton: Skeleton) -> Skeleton:
    return Skeleton.model_validate(copy.deepcopy(skeleton.model_dump()))
