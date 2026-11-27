"""对审计日志做纯统计的异常检查。

这里**不判断对错**，只挑出「值得看一眼」的调用。

设计边界：
- 只看日志里已有的字段，不发网络请求、不调模型，成本为零
- 结论不写进日志（不改哈希链），只在报告里算
- 一条规则命中一组时只报一条，避免「90% 都标红」这种没用的噪声
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .crypto import sha256_hex

# audit._sha("") 的口径不是 sha256(b"")，而是 sha256_hex({"text": ""})
EMPTY_SHA256 = sha256_hex({"text": ""})

RULE_LABELS = {
    "token_spike": "token 突增",
    "duplicate_prompt": "重复输入",
    "empty_response": "空响应",
    "zero_tokens": "tokens 为 0",
}


@dataclass(frozen=True)
class Thresholds:
    """阈值。默认值偏保守——宁可少报，不要让人习惯性忽略。"""

    min_samples: int = 20        # 每个模型至少这么多样本才判 token 突增
    spike_factor: float = 3.0    # 超过同模型 P95 的这么多倍算突增
    duplicate_min: int = 20      # 同一输入出现这么多次
    duplicate_outputs: int = 5   # 且产生了这么多种不同输出，才算「像卡住」


@dataclass(frozen=True)
class Finding:
    rule: str
    call_id: str                       # 代表调用，用于展示
    detail: str
    call_ids: tuple[str, ...] = field(default=())  # 受影响的全部调用
    group: bool = False                # True = 组级命中，行上只标代表调用

    def all_ids(self) -> tuple[str, ...]:
        return self.call_ids or (self.call_id,)


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return float(ordered[idx])


def detect(calls: list[dict[str, Any]], *, thresholds: Thresholds | None = None) -> list[Finding]:
    """返回按规则挑出的调用。calls 是 build_report 里那种扁平 dict。"""
    th = thresholds or Thresholds()
    findings: list[Finding] = []

    # 1) token 突增：按模型分组，和同模型的 P95 比
    by_model: dict[str, list[int]] = {}
    for call in calls:
        model = str(call.get("model") or "")
        if model:
            by_model.setdefault(model, []).append(int(call.get("tokens") or 0))
    for model, toks in by_model.items():
        if len(toks) < th.min_samples:
            continue
        p95 = _percentile(toks, 0.95)
        if p95 <= 0:
            continue
        cutoff = p95 * th.spike_factor
        for call in calls:
            if str(call.get("model") or "") != model:
                continue
            tokens = int(call.get("tokens") or 0)
            if tokens > cutoff:
                findings.append(
                    Finding(
                        "token_spike",
                        str(call.get("call_id") or ""),
                        f"{tokens} tokens，同模型 P95 是 {int(p95)}（{th.spike_factor:g}× 阈值）",
                    )
                )

    # 2) 重复输入：同一 prompt 反复跑且输出发散——像卡在重试里。
    #    一条命中只报一条，否则一轮对话几十步会全部标红。
    by_prompt: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        key = str(call.get("prompt_sha256") or "")
        if key:
            by_prompt.setdefault(key, []).append(call)
    for _key, group in by_prompt.items():
        if len(group) < th.duplicate_min:
            continue
        outs = {str(g.get("response_sha256") or "") for g in group}
        if len(outs) < th.duplicate_outputs:
            continue
        ids = tuple(str(g.get("call_id") or "") for g in group)
        findings.append(
            Finding(
                "duplicate_prompt",
                ids[0],
                f"同一输入出现 {len(group)} 次，产生 {len(outs)} 种不同输出",
                ids,
                group=True,
            )
        )

    # 3) 空响应 / 4) tokens 为 0
    for call in calls:
        resp = str(call.get("response_sha256") or "")
        if resp == EMPTY_SHA256:
            findings.append(Finding("empty_response", str(call.get("call_id") or ""), "输出为空"))
        elif int(call.get("tokens") or 0) == 0:
            findings.append(
                Finding("zero_tokens", str(call.get("call_id") or ""), "有输出但记录里 tokens 是 0")
            )

    return findings


__all__ = ["EMPTY_SHA256", "RULE_LABELS", "Finding", "Thresholds", "detect"]
