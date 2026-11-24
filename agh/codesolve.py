"""多候选求解 + 测试选择：AGH「多个子级 → 独立验证 → 仲裁」思路在代码任务上的最小实现。

求解策略 `SolverPolicy` 是有界基因组（取值范围固定，变异不会越界）：
- n_samples：每题采样几个候选；
- select：怎么选最终候选，**只能用 visible 用例**，hidden 只用于最后评估；
- hint：提示词附加说明；
- rounds：几轮「跑公开用例 → 带着失败信息重写」。这是唯一能改变单次生成质量的维度，
  其余三个都只是生成前/生成后的选择。

重要的边界：
- 从 N 个候选里挑一个，上限是「N 个里至少有一个对」（pass@N）。选择策略不能创造模型没有的能力。
- visible 测试能过滤明显错误，但挡不住「过了 visible 却在 hidden 上错」的候选，这部分差距会如实体现在分数里。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .codetasks import CodeTask
from .execverify import run_cases

N_SAMPLES_CHOICES = (1, 2, 3, 5, 8)
SELECT_CHOICES = ("first", "visible_best", "visible_best_shortest")
HINT_CHOICES = ("plain", "edge_cases", "step_by_step")
ROUND_CHOICES = (1, 2, 3)

_HINTS = {
    "plain": "",
    "edge_cases": "\n注意空输入、重复元素、边界值。",
    "step_by_step": "\n先在心里列出算法步骤，再写代码。",
}
_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class SolverPolicy:
    n_samples: int = 1
    select: str = "first"
    hint: str = "plain"
    rounds: int = 1

    def __post_init__(self) -> None:
        if self.n_samples not in N_SAMPLES_CHOICES:
            raise ValueError(f"n_samples 越界: {self.n_samples}")
        if self.select not in SELECT_CHOICES:
            raise ValueError(f"select 越界: {self.select}")
        if self.hint not in HINT_CHOICES:
            raise ValueError(f"hint 越界: {self.hint}")
        if self.rounds not in ROUND_CHOICES:
            raise ValueError(f"rounds 越界: {self.rounds}")

    def key(self) -> str:
        return f"n{self.n_samples}|{self.select}|{self.hint}|r{self.rounds}"


def extract_code(text: str) -> str:
    m = _FENCE.search(text)
    return (m.group(1) if m else text).strip()


def build_prompt(
    task: CodeTask, policy: SolverPolicy, sample_index: int, feedback: str = ""
) -> str:
    # 样本序号写进提示：对确定性客户端或带缓存的网关，保证每次采样的输入不同
    tail = f"\n（第 {sample_index + 1} 次尝试）"
    return f"{task.prompt}{_HINTS[policy.hint]}{feedback}{tail}"


def format_feedback(code: str, task: CodeTask, result: Any) -> str:
    """把公开用例的失败整理成可读反馈。只给 visible——hidden 永远不进提示。"""
    if not result.failed_cases:
        return ""
    lines = ["\n\n上一版代码在公开用例上失败："]
    for idx in result.failed_cases[:3]:
        case = task.spec.visible[idx]
        got = result.outputs[idx] if idx < len(result.outputs) else None
        lines.append(f"- 输入 {list(case.args)!r}，期望 {case.expected!r}，实际 {got!r}")
    lines.append("请修正后重新给出完整代码。")
    return "\n".join(lines)


@dataclass(frozen=True)
class SolveOutcome:
    task_id: str
    chosen_code: str
    calls: int
    visible_scores: tuple[float, ...]
    hidden_score: float  # 只用于评估，不参与选择
    oracle_hit: bool  # N 个候选里是否至少有一个 hidden 全对（pass@N 的上限）
    call_errors: int = 0  # 模型调用失败的次数；与「模型答错」分开记，否则会误判能力


def solve_task(task: CodeTask, complete: Callable[[str], str], policy: SolverPolicy) -> SolveOutcome:
    codes: list[str] = []
    errors = 0
    feedback = ""
    for round_index in range(policy.rounds):
        for i in range(policy.n_samples):
            try:
                codes.append(extract_code(complete(build_prompt(task, policy, i, feedback))))
            except Exception:  # 网络或模型错误按空候选处理，不中断整轮评估
                codes.append("")
                errors += 1
        if round_index == policy.rounds - 1:
            break
        # 用本轮最好的候选跑公开用例，把失败信息带进下一轮
        best_code = max(codes, key=lambda c: run_cases(c, task.spec, task.spec.visible).score)
        result = run_cases(best_code, task.spec, task.spec.visible)
        if result.score >= 1.0:
            break
        feedback = format_feedback(best_code, task, result)
    vis = [run_cases(c, task.spec, task.spec.visible).score for c in codes]
    if policy.select == "first" and policy.rounds > 1:
        # 多轮的语义是「越改越好」：此时「取第一个」等于丢掉修正结果，
        # 所以多轮下按 visible 选，单轮保持 first 的原义。
        idx = max(range(len(codes)), key=lambda i: (vis[i], -i))
    elif policy.select == "first":
        idx = 0
    else:
        best = max(vis)
        pool = [i for i, v in enumerate(vis) if v == best]
        idx = min(pool, key=lambda i: (len(codes[i]), i)) if policy.select == "visible_best_shortest" else pool[0]
    hidden = run_cases(codes[idx], task.spec, task.spec.hidden).score
    oracle = hidden == 1.0 or any(
        run_cases(c, task.spec, task.spec.hidden).score == 1.0 for j, c in enumerate(codes) if j != idx
    )
    return SolveOutcome(
        task.spec.task_id,
        codes[idx],
        policy.n_samples * policy.rounds,
        tuple(vis),
        hidden,
        oracle,
        errors,
    )


__all__ = [
    "ROUND_CHOICES",
    "SolveOutcome",
    "SolverPolicy",
    "build_prompt",
    "extract_code",
    "format_feedback",
    "solve_task",
]
