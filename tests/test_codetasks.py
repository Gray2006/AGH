from __future__ import annotations

from agh.codetasks import TASKS
from agh.execverify import run_cases


def test_task_count():
    assert len(TASKS) == 15


def test_reference_solutions_pass_visible_and_hidden():
    for tid, t in TASKS.items():
        assert run_cases(t.reference, t.spec, t.spec.visible).score == 1.0, tid
        assert run_cases(t.reference, t.spec, t.spec.hidden).score == 1.0, tid


def test_every_mutant_is_killed_by_hidden_cases():
    """hidden 用例必须能杀死每个已知 bug 变体，否则测试太弱。"""
    for tid, t in TASKS.items():
        assert t.mutants, tid
        for i, m in enumerate(t.mutants):
            assert run_cases(m, t.spec, t.spec.hidden).score < 1.0, f"{tid} mutant {i} 逃过了 hidden"


def test_prompt_does_not_leak_hidden_cases():
    for tid, t in TASKS.items():
        for c in t.spec.hidden:
            assert f"{t.spec.entrypoint}{c.args!r}" not in t.prompt, tid


def test_search_always_evaluates_one_candidate() -> None:
    """预算是软上限：预算比单次成本还小时，至少跑完一个候选，否则无从比较。"""
    from agh.code_evolution import random_search
    from agh.codetasks import TASKS
    from agh.simulated import SimulatedCoder

    train = list(TASKS.values())[:6]
    result = random_search(train, SimulatedCoder(seed=0), call_budget=1, seed=0)
    assert result.evaluations == 1
    assert result.calls_spent >= len(train)  # 超出预算，但完成了一个候选


def test_call_errors_are_not_scored_as_wrong_answers() -> None:
    """模型调用失败要单独计数，否则 402/超时会被读成「模型全答错」。"""
    from agh.codesolve import SolverPolicy, solve_task
    from agh.codetasks import TASKS

    def broken(_prompt: str) -> str:
        raise RuntimeError("HTTP Error 402: Payment Required")

    outcome = solve_task(TASKS["dedupe"], broken, SolverPolicy(n_samples=3))
    assert outcome.call_errors == 3
    assert outcome.hidden_score == 0.0
