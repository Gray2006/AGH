"""子级的 LLM 适配层。

M0 的子级是规则函数。这里把「接真模型」这件事做成可插拔的：
调用方只提供一个 `complete(prompt) -> str` 的传输函数（HTTP、SDK、本地模型都行），
适配层负责三件事——拼提示、抽 JSON、按契约 schema 校验。

刻意不内置任何网络代码：模型怎么调是部署方的事，框架只约束输出形状。
校验失败抛 ChildOutputError，带上 jsonschema 的具体错误路径，方便重试或换模型。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from jsonschema import Draft7Validator

from .contracts import Contract, GestaltReconstruction, Skeleton, reconstruction_schema

Completion = Callable[[str], str]


class ChildOutputError(ValueError):
    """子级输出不符合契约。保留原始文本与错误列表，便于调用方决定重试。"""

    def __init__(self, message: str, *, raw: str = "", errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.raw = raw
        self.errors = errors or []


class ReconstructChild(Protocol):
    """所有子级（规则或 LLM）统一的调用形状。"""

    def reconstruct(self, contract_id: str) -> GestaltReconstruction: ...


@dataclass(frozen=True)
class RuleChild:
    """把 M0 的规则函数包成统一接口，实验里可以和 LLM 子级混跑。"""

    name: str
    fn: Callable[[str], GestaltReconstruction]

    def reconstruct(self, contract_id: str) -> GestaltReconstruction:
        return self.fn(contract_id)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """从模型回复里取 JSON：优先代码围栏，其次第一个平衡的 {...}。"""
    candidate = text.strip()
    fenced = _JSON_FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    start = candidate.find("{")
    if start < 0:
        raise ChildOutputError("回复里没有 JSON 对象", raw=text)
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(candidate[start : index + 1])
                except json.JSONDecodeError as exc:
                    raise ChildOutputError(f"JSON 解析失败：{exc}", raw=text) from exc
    raise ChildOutputError("JSON 括号不闭合", raw=text)


def build_prompt(contract: Contract, parent_features: list[str] | None = None) -> str:
    """把骨架、必需项、垂直移动写成可执行的指令，不给答案。"""
    sk = contract.skeleton
    lines = [
        "你在做一次「整体重构」，不是零件拼接。",
        "根据下面的骨架，输出一个 JSON 对象，描述你对整体的重构结果。",
        "",
        f"骨架 {sk.skeleton_id}",
        f"- 节点：{', '.join(sk.nodes)}",
        f"- 边：{'; '.join(f'{a}->{b}' for a, b in sk.edges)}",
        f"- 必须覆盖：{', '.join(sk.required_items)}",
    ]
    if sk.moves:
        moves = "; ".join(
            f"{m.node}:{'垂直' if m.vertical else '水平'}"
            + (f"(声明深度 {m.declared_depth}, 保留深度 {m.preserved_depth})" if m.vertical else "")
            for m in sk.moves
        )
        lines.append(f"- 移动：{moves}")
    if sk.min_vertical_moves > 0:
        lines.append(f"- 至少 {sk.min_vertical_moves} 次垂直移动，写在 content.vertical_moves 里")
    if parent_features:
        lines.append(f"- 父级签名特征（用于判断你是否只是复读）：{', '.join(parent_features)}")
    lines += [
        "",
        "只输出 JSON，字段：",
        "child_id, contract_id, skeleton_id,",
        "parts (数组，必须包含上面的必需项),",
        'coverage: {"covered": [...]},',
        'signature: {"signature_id": "...", "features": [...], "abstraction": false},',
        "self_confidence (0-1),",
        'content: {"edges": [[a,b],...], "vertical_moves": [...], "changed_nodes": [...]}',
        "",
        f"contract_id 固定为 {contract.contract_id}，skeleton_id 固定为 {sk.skeleton_id}。",
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class LlmChild:
    """一个 LLM 子级：调用方给传输函数，框架校验输出。"""

    name: str
    complete: Completion
    skeleton: Skeleton
    parent_features: list[str] | None = None

    def reconstruct(self, contract_id: str) -> GestaltReconstruction:
        contract = Contract(
            contract_id=contract_id,
            parent_id="llm-parent",
            skeleton=self.skeleton,
            budget_max_tokens=1,
            ttl_ms=1,
        )
        prompt = build_prompt(contract, self.parent_features)
        raw = self.complete(prompt)
        data = extract_json(raw)
        if not isinstance(data, dict):
            raise ChildOutputError("顶层必须是 JSON 对象", raw=raw)
        data = dict(data)
        data.setdefault("child_id", self.name)
        data.setdefault("contract_id", contract_id)
        data.setdefault("skeleton_id", self.skeleton.skeleton_id)
        schema = reconstruction_schema(self.skeleton)
        errors = sorted(Draft7Validator(schema).iter_errors(data), key=lambda e: list(e.path))
        if errors:
            messages = [
                f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
            ]
            raise ChildOutputError(
                f"输出不符合契约（{len(messages)} 处）：{messages[0]}", raw=raw, errors=messages
            )
        try:
            return GestaltReconstruction.model_validate(data)
        except Exception as exc:  # pydantic 错误也归到同一出口
            raise ChildOutputError(f"模型校验失败：{exc}", raw=raw) from exc


def as_rule_child(name: str, fn: Callable[[str], GestaltReconstruction]) -> RuleChild:
    return RuleChild(name=name, fn=fn)


__all__ = [
    "ChildOutputError",
    "Completion",
    "LlmChild",
    "ReconstructChild",
    "RuleChild",
    "as_rule_child",
    "build_prompt",
    "extract_json",
]
