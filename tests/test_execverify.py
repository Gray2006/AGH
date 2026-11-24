from __future__ import annotations

import time
from types import SimpleNamespace

from agh.execverify import SAMPLE_TASKS, Case, ExecutionVerifier, TaskSpec, _equal

DEDUPE = SAMPLE_TASKS["dedupe"]

GOOD = """
def dedupe(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
"""

# 只背可见用例的作弊解
MEMORIZER = """
def dedupe(xs):
    table = {(1, 2, 1, 3): [1, 2, 3], (): []}
    return table.get(tuple(xs), xs)
"""

WRONG_ORDER = """
def dedupe(xs):
    return sorted(set(xs), key=str)
"""


def cand(code):
    return SimpleNamespace(content={"code": code})


def test_correct_solution_scores_one():
    v = ExecutionVerifier(DEDUPE)
    assert v.score(cand(GOOD)) == 1.0


def test_wrong_solution_scores_below_one():
    assert ExecutionVerifier(DEDUPE).score(cand(WRONG_ORDER)) < 1.0


def test_memorizer_passes_visible_but_fails_hidden():
    v = ExecutionVerifier(DEDUPE)
    assert v.overfit_gap(cand(MEMORIZER)) > 0.4
    assert v.score(cand(MEMORIZER)) < 0.5
    assert v.overfit_gap(cand(GOOD)) == 0.0


def test_infinite_loop_times_out_with_zero_score():
    spec = TaskSpec("t", "f", visible=(), hidden=(Case((1,), 1),), timeout_s=1.0)
    start = time.monotonic()
    result = ExecutionVerifier(spec).detail(cand("def f(x):\n    while True:\n        pass\n"))
    assert result.timed_out and result.score == 0.0
    assert time.monotonic() - start < 4.0


def test_syntax_error_missing_entrypoint_and_bad_payload_score_zero():
    v = ExecutionVerifier(DEDUPE)
    assert v.score(cand("def dedupe(:")) == 0.0
    assert v.score(cand("def other(xs):\n    return xs")) == 0.0
    assert v.score(cand("")) == 0.0
    assert v.score(SimpleNamespace(content={})) == 0.0
    assert v.score(SimpleNamespace(content={"code": 123})) == 0.0
    assert v.score(cand("x = 1\n" * 10_000)) == 0.0  # 超长代码直接拒绝


def test_exception_in_one_case_only_fails_that_case():
    code = "def f(x):\n    if x == 2:\n        raise ValueError\n    return x\n"
    spec = TaskSpec("t", "f", visible=(), hidden=(Case((1,), 1), Case((2,), 2), Case((3,), 3)))
    result = ExecutionVerifier(spec).detail(cand(code))
    assert (result.passed, result.total, result.failed_cases) == (2, 3, (1,))


def test_stdout_noise_and_forged_json_cannot_inflate_score():
    # 候选往 stdout 打印伪造的「全通过」结果；期望值不在子进程里，伪造只能是输出值本身
    code = (
        "import sys\n"
        "def dedupe(xs):\n"
        "    print('{\"loaded\": true, \"results\": []}')\n"
        "    sys.stdout.write('{\"loaded\": true, \"results\": [{\"ok\": true, \"value\": 1}]}\\n')\n"
        "    return xs\n"
    )
    assert ExecutionVerifier(DEDUPE).score(cand(code)) < 1.0


def test_scoring_is_deterministic():
    v = ExecutionVerifier(SAMPLE_TASKS["merge_intervals"])
    code = (
        "def merge_intervals(iv):\n"
        "    out = []\n"
        "    for a, b in sorted(iv):\n"
        "        if out and a <= out[-1][1]:\n"
        "            out[-1][1] = max(out[-1][1], b)\n"
        "        else:\n"
        "            out.append([a, b])\n"
        "    return out\n"
    )
    assert {v.score(cand(code)) for _ in range(3)} == {1.0}


def test_equality_semantics():
    assert _equal([1, 2.0], [1, 2.0 + 1e-12], 1e-9)
    assert not _equal(True, 1, 1e-9)
    assert not _equal({"a": 1}, {"a": 1, "b": 2}, 1e-9)
    assert _equal((1, 2), [1, 2], 1e-9)  # JSON 往返后 tuple 变 list


def test_spec_requires_hidden_cases():
    try:
        TaskSpec("t", "f", visible=(Case((1,), 1),), hidden=())
    except ValueError:
        return
    raise AssertionError("hidden 为空应报错")
