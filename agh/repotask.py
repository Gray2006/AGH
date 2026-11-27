"""仓库级任务：真实 bug 的隔离执行与判定。

这是 AGI 线的第一块基础设施。之前所有任务都是「一个 Case 对象 + 纯函数打分」，
模型满分、没有梯度。仓库级任务换成：读多文件 → 改代码 → 跑测试才知道对不对。

边界（重要）：
- 候选只看得到 `issue`，看不到 `hidden_tests`
- 每次判定都在临时目录的副本里跑，不改动原仓库
- 子进程超时即判失败
- 补丁应用失败和不通过分开记：前者是格式问题，后者是能力问题
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RepoTask:
    """一道仓库级任务。"""

    name: str
    repo: Path                      # 仓库快照（含 .git）
    issue: str                      # 给候选看的描述
    hidden_tests: tuple[str, ...]   # 判定用命令，候选看不到
    base_ref: str = "HEAD"
    timeout_s: int = 120
    # 跑测试前的准备命令（如 pip install -e ".[dev]"）；空表示不需要
    setup: tuple[str, ...] = ()
    # 额外环境变量。src 布局的仓库通常要 PYTHONPATH=src
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TaskResult:
    """一次判定的结果。"""

    passed: bool
    applied: bool                   # 补丁是否成功应用
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    reason: str = ""                # 失败原因（给人看的一句话）
    outputs: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "applied": self.applied,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 2),
            "reason": self.reason,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-4000:],
        }


def _git(args: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def apply_patch(repo: Path, patch: str) -> tuple[bool, str]:
    """在 repo 里应用 unified diff。返回 (成功与否, 说明)。"""
    if not patch.strip():
        return False, "补丁为空"

    def _apply(extra: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "apply", *extra, "-p1", "--whitespace=nowarn", "-"],
            cwd=repo,
            input=patch,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    check = _apply(["--check"])
    if check.returncode != 0:
        detail = (check.stderr or check.stdout).strip()[:300]
        return False, f"补丁无法应用：{detail}"

    applied = _apply([])
    if applied.returncode != 0:
        detail = (applied.stderr or applied.stdout).strip()[:300]
        return False, f"补丁应用失败：{detail}"
    return True, ""


def run_task(
    task: RepoTask,
    *,
    candidate_patch: str | None = None,
    keep_dir: Path | None = None,
) -> TaskResult:
    """跑一次判定。

    `candidate_patch=None` 表示不应用任何补丁——用来跑基线（原仓库应该失败）。
    """
    started = time.perf_counter()
    repo = Path(task.repo).resolve()
    if not repo.exists():
        return TaskResult(
            passed=False, applied=False, exit_code=-1, stdout="", stderr="",
            duration_s=0.0, reason=f"仓库不存在：{repo}",
        )

    root = Path(keep_dir) if keep_dir else Path(tempfile.mkdtemp(prefix="agh-repotask-"))
    work = root / "repo"
    try:
        shutil.copytree(repo, work, symlinks=True)

        # 固定到 base_ref，保证可复现
        checkout = _git(["checkout", "--quiet", task.base_ref], work)
        if checkout.returncode != 0:
            return TaskResult(
                passed=False, applied=False, exit_code=-1, stdout="", stderr="",
                duration_s=time.perf_counter() - started,
                reason=f"切不到 {task.base_ref}：{(checkout.stderr or checkout.stdout).strip()[:200]}",
            )

        if candidate_patch is not None:
            ok, why = apply_patch(work, candidate_patch)
            if not ok:
                return TaskResult(
                    passed=False, applied=False, exit_code=-1, stdout="", stderr="",
                    duration_s=time.perf_counter() - started, reason=why,
                )

        env = os.environ.copy()
        for key, value in task.env:
            env[key] = value

        for cmd in task.setup:
            try:
                prep = subprocess.run(
                    cmd, cwd=work, shell=True, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=task.timeout_s, env=env,
                )
            except subprocess.TimeoutExpired:
                return TaskResult(
                    passed=False, applied=True, exit_code=-1, stdout="", stderr="",
                    duration_s=time.perf_counter() - started,
                    reason=f"准备步骤超时：{cmd}",
                )
            if prep.returncode != 0:
                tail = (prep.stderr or prep.stdout or "").strip()[-300:]
                return TaskResult(
                    passed=False, applied=True, exit_code=-1, stdout="", stderr="",
                    duration_s=time.perf_counter() - started,
                    reason=f"准备步骤失败：{cmd} -> {tail}",
                )

        outputs: list[str] = []
        exit_code = 0
        combined_out = ""
        combined_err = ""
        for cmd in task.hidden_tests:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=work,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=task.timeout_s,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                return TaskResult(
                    passed=False, applied=True, exit_code=-1,
                    stdout=combined_out, stderr=combined_err,
                    duration_s=time.perf_counter() - started,
                    reason=f"超时（>{task.timeout_s}s）：{cmd}",
                    outputs=tuple(outputs),
                )
            combined_out += proc.stdout or ""
            combined_err += proc.stderr or ""
            outputs.append(f"{cmd} -> {proc.returncode}")
            if proc.returncode != 0:
                exit_code = proc.returncode
                break

        passed = exit_code == 0
        return TaskResult(
            passed=passed,
            applied=True,
            exit_code=exit_code,
            stdout=combined_out,
            stderr=combined_err,
            duration_s=time.perf_counter() - started,
            reason="" if passed else "测试未全绿",
            outputs=tuple(outputs),
        )
    finally:
        if keep_dir is None:
            shutil.rmtree(root, ignore_errors=True)


__all__ = ["RepoTask", "TaskResult", "apply_patch", "run_task"]
