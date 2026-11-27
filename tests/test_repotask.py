from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agh.repotask import RepoTask, apply_patch, run_task

BUGGY = '''def add(a, b):
    return a - b
'''

FIXED = '''def add(a, b):
    return a + b
'''

TEST = '''from calc import add


def test_add():
    assert add(2, 3) == 5
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "calc.py").write_text(BUGGY, encoding="utf-8")
    (repo / "test_calc.py").write_text(TEST, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "buggy add")
    return repo


def _task(repo: Path) -> RepoTask:
    return RepoTask(
        name="demo",
        repo=repo,
        issue="add() 返回了错误的结果",
        hidden_tests=(f'"{sys.executable}" -m pytest -q',),
        timeout_s=60,
    )


PATCH = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""

BAD_PATCH = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a * b
"""


def test_baseline_fails_without_patch(tmp_path: Path) -> None:
    """原仓库应该是坏的——否则这道题没有区分度。"""
    result = run_task(_task(_make_repo(tmp_path)))
    assert result.passed is False
    assert result.applied is True


def test_correct_patch_passes(tmp_path: Path) -> None:
    result = run_task(_task(_make_repo(tmp_path)), candidate_patch=PATCH)
    assert result.passed is True, result.reason + result.stdout
    assert result.applied is True


def test_wrong_patch_fails(tmp_path: Path) -> None:
    result = run_task(_task(_make_repo(tmp_path)), candidate_patch=BAD_PATCH)
    assert result.passed is False
    assert result.applied is True
    assert "测试未全绿" in result.reason


def test_unappliable_patch_is_distinguished(tmp_path: Path) -> None:
    """补丁都贴不上，和「改错了」要分开记。"""
    junk = "--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n"
    result = run_task(_task(_make_repo(tmp_path)), candidate_patch=junk)
    assert result.passed is False
    assert result.applied is False
    assert "补丁" in result.reason


def test_original_repo_untouched(tmp_path: Path) -> None:
    """判定必须在副本里跑，原仓库不能被改。"""
    repo = _make_repo(tmp_path)
    run_task(_task(repo), candidate_patch=PATCH)
    assert (repo / "calc.py").read_text(encoding="utf-8") == BUGGY


def test_timeout_is_reported(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    task = RepoTask(
        name="slow",
        repo=repo,
        issue="x",
        hidden_tests=(f'"{sys.executable}" -c "import time; time.sleep(5)"',),
        timeout_s=1,
    )
    result = run_task(task)
    assert result.passed is False
    assert "超时" in result.reason


def test_apply_patch_reports_empty() -> None:
    ok, why = apply_patch(Path("."), "   ")
    assert ok is False
    assert "空" in why


@pytest.mark.parametrize("patch", [PATCH])
def test_result_as_dict(patch: str, tmp_path: Path) -> None:
    result = run_task(_task(_make_repo(tmp_path)), candidate_patch=patch)
    payload = result.as_dict()
    assert payload["passed"] is True
    assert "duration_s" in payload
