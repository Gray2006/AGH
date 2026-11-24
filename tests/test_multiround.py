from __future__ import annotations

import pytest

from agh.codesolve import SolverPolicy, build_prompt, solve_task
from agh.codetasks import TASKS


def test_rounds_bounded() -> None:
    with pytest.raises(ValueError):
        SolverPolicy(rounds=4)


def test_multi_round_feeds_back_failures() -> None:
    """第一轮写错 → 第二轮提示里必须带失败信息 → 修对。"""
    task = TASKS["dedupe"]
    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return "```python\ndef dedupe(items):\n    return items\n```"
        return f"```python\n{task.reference}\n```"

    outcome = solve_task(task, complete, SolverPolicy(n_samples=1, rounds=2))
    assert len(prompts) == 2
    assert "上一版代码在公开用例上失败" in prompts[1]
    assert outcome.hidden_score == 1.0
    assert outcome.calls == 2


def test_feedback_never_leaks_hidden_cases() -> None:
    task = TASKS["dedupe"]
    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "```python\ndef dedupe(items):\n    return items\n```"

    solve_task(task, complete, SolverPolicy(n_samples=1, rounds=2))
    hidden_expected = [repr(c.expected) for c in task.spec.hidden]
    # 反馈里只应出现 visible 的期望值；hidden 的期望值一个都不能出现
    for expected in hidden_expected:
        if expected in ("[]", "[1, 2]"):
            continue  # 与 visible 重合的值无法区分，跳过
        assert expected not in prompts[1]


def test_single_round_has_no_feedback() -> None:
    task = TASKS["dedupe"]
    prompts: list[str] = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "```python\ndef dedupe(items):\n    return items\n```"

    solve_task(task, complete, SolverPolicy(n_samples=1, rounds=1))
    assert len(prompts) == 1
    assert "上一版代码" not in prompts[0]


def test_prompt_includes_round_hint() -> None:
    task = TASKS["dedupe"]
    prompt = build_prompt(task, SolverPolicy(rounds=2), 0, feedback="\n\n上一版代码在公开用例上失败：")
    assert "上一版代码在公开用例上失败" in prompt
