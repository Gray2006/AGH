"""执行型验证器：用「真跑代码 + 留出测试」取代「按同一规则造题再按同一规则打分」。

动机（见 docs/STATUS.md 已知限制 2、3、11）：现有 StructuralVerifier 的校准负样本由同一条规则构造，
验证的是「规则被正确实现」，不是「规则在语义上正确」。要让 AGH 的任何改进可证伪，需要一个
**不由 AGH 自己定义对错** 的信号。可执行测试是最便宜的这类信号。

设计要点
1. 期望值永远留在父进程。子进程只拿到入参、只回传输出；候选无从得知期望，也就无法伪造「通过」，
   伪造输出等价于算出正确答案。
2. 测试分两组：visible 可以写进 prompt 给子级看，hidden 只给验证器用。硬编码 visible 用例的候选
   在 hidden 上得 0，这正是「过拟合可见测试」的检测手段。
3. 评分是确定性的：同一份代码、同一组用例，得分相同（PYTHONHASHSEED 固定，不读时钟与随机数）。
4. 只依赖标准库，满足既有 `Verifier` 协议：`score(candidate, skeleton) -> float`。

安全边界（务必读）
- 这里用 subprocess + rlimit + 超时 + 清空环境 + 临时目录，**只防失控，不防恶意**：
  不隔离网络与文件系统读权限。评估不可信模型输出时，请把整个进程放进容器 / gVisor / 无网络沙箱。
- `preexec_fn` 在多线程程序里不完全安全；并行评估请用多进程而非多线程。
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 避免在运行期引入 pydantic 依赖链
    from .contracts import GestaltReconstruction, Skeleton

MAX_CODE_CHARS = 20_000
_MEM_LIMIT_BYTES = 512 * 1024 * 1024

# 子进程入口：只读入参、只写输出。不接触期望值。
_HARNESS = r"""
import json, os, sys
_real_stdout = os.fdopen(os.dup(1), "w")
sys.stdout = open(os.devnull, "w")
sys.stderr = open(os.devnull, "w")
payload = json.loads(sys.stdin.read())
ns = {"__name__": "candidate"}
out = {"loaded": False, "results": []}
try:
    exec(compile(payload["code"], "<candidate>", "exec"), ns)
    fn = ns[payload["entrypoint"]]
    out["loaded"] = callable(fn)
except BaseException:
    fn = None
if out["loaded"]:
    for args in payload["cases"]:
        try:
            value = fn(*args)
            json.dumps(value)
            out["results"].append({"ok": True, "value": value})
        except BaseException:
            out["results"].append({"ok": False})
_real_stdout.write("\n" + json.dumps(out) + "\n")
_real_stdout.flush()
os._exit(0)
"""


@dataclass(frozen=True)
class Case:
    """一条测试：入参列表 + 期望返回值（均需可 JSON 序列化）。"""

    args: tuple[Any, ...]
    expected: Any


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    entrypoint: str
    visible: tuple[Case, ...]
    hidden: tuple[Case, ...]
    timeout_s: float = 5.0
    float_tol: float = 1e-9

    def __post_init__(self) -> None:
        if not self.hidden:
            raise ValueError("hidden 用例不能为空：否则无法检测过拟合可见测试")


@dataclass(frozen=True)
class ExecResult:
    passed: int
    total: int
    loaded: bool
    timed_out: bool
    failed_cases: tuple[int, ...] = field(default_factory=tuple)

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _equal(a: Any, b: Any, tol: float) -> bool:
    """JSON 语义下的相等；浮点按容差；bool 不与数字混淆。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) or isinstance(b, float):
            return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
        return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_equal(x, y, tol) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k], tol) for k in a)
    return bool(a == b)


def _limits(cpu_s: int):
    def apply() -> None:
        try:
            import resource

            # Windows 没有 resource 模块；类型存根也只覆盖 POSIX，故逐行忽略
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))  # type: ignore[attr-defined]
            resource.setrlimit(  # type: ignore[attr-defined]
                resource.RLIMIT_AS, (_MEM_LIMIT_BYTES, _MEM_LIMIT_BYTES)  # type: ignore[attr-defined]
            )
            resource.setrlimit(  # type: ignore[attr-defined]
                resource.RLIMIT_FSIZE, (1_000_000, 1_000_000)  # type: ignore[attr-defined]
            )
        except (ImportError, ValueError, OSError):
            pass  # 非 POSIX 或受限环境：退回仅靠超时

    return apply


def run_cases(code: str, spec: TaskSpec, cases: Sequence[Case]) -> ExecResult:
    """在子进程里跑 `cases`，期望值只在本进程比较。"""
    total = len(cases)
    if not isinstance(code, str) or not code.strip() or len(code) > MAX_CODE_CHARS:
        return ExecResult(0, total, loaded=False, timed_out=False)
    payload = json.dumps(
        {"code": code, "entrypoint": spec.entrypoint, "cases": [list(c.args) for c in cases]}
    )
    env = {"PYTHONHASHSEED": "0", "PATH": os.environ.get("PATH", "")}
    with tempfile.TemporaryDirectory(prefix="agh-exec-") as workdir:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", _HARNESS],
                input=payload,
                capture_output=True,
                text=True,
                timeout=spec.timeout_s,
                cwd=workdir,
                env=env,
                start_new_session=True,
                preexec_fn=_limits(math.ceil(spec.timeout_s) + 1) if os.name == "posix" else None,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(0, total, loaded=True, timed_out=True)
    parsed = _parse_last_json(proc.stdout)
    if parsed is None or not parsed.get("loaded"):
        return ExecResult(0, total, loaded=False, timed_out=False)
    results = parsed.get("results", [])
    if len(results) != total:  # 子进程中途崩溃（如 OOM / CPU 超限）
        return ExecResult(0, total, loaded=True, timed_out=False)
    passed, failed = 0, []
    for i, (case, got) in enumerate(zip(cases, results, strict=True)):
        if got.get("ok") and _equal(got.get("value"), case.expected, spec.float_tol):
            passed += 1
        else:
            failed.append(i)
    return ExecResult(passed, total, loaded=True, timed_out=False, failed_cases=tuple(failed))


def _parse_last_json(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            return value if isinstance(value, dict) else None
    return None


@dataclass(frozen=True)
class ExecutionVerifier:
    """满足 `agh.verifier.Verifier` 协议。代码取自 `candidate.content["code"]`。

    默认只用 hidden 用例打分；`include_visible=True` 时两组合并（仅用于调试，
    会削弱过拟合检测）。`skeleton` 参数为兼容协议而保留，此处不使用。
    """

    spec: TaskSpec
    include_visible: bool = False
    name: str = "execution"

    def _cases(self) -> tuple[Case, ...]:
        if self.include_visible:
            return self.spec.visible + self.spec.hidden
        return self.spec.hidden

    def detail(self, candidate: GestaltReconstruction) -> ExecResult:
        code = candidate.content.get("code") if isinstance(candidate.content, dict) else None
        cases = self._cases()
        if not isinstance(code, str):
            return ExecResult(0, len(cases), loaded=False, timed_out=False)
        return run_cases(code, self.spec, cases)

    def score(self, candidate: GestaltReconstruction, skeleton: Skeleton | None = None) -> float:
        return self.detail(candidate).score

    def overfit_gap(self, candidate: GestaltReconstruction) -> float:
        """visible 得分减 hidden 得分。接近 1 说明候选在背可见答案。"""
        code = candidate.content.get("code") if isinstance(candidate.content, dict) else None
        if not isinstance(code, str):
            return 0.0
        vis = run_cases(code, self.spec, self.spec.visible).score
        hid = run_cases(code, self.spec, self.spec.hidden).score
        return vis - hid


def _c(*args: Any, expected: Any) -> Case:
    return Case(tuple(args), expected)


SAMPLE_TASKS: dict[str, TaskSpec] = {
    "dedupe": TaskSpec(
        task_id="dedupe",
        entrypoint="dedupe",
        visible=(_c([1, 2, 1, 3], expected=[1, 2, 3]), _c([], expected=[])),
        hidden=(
            _c(["a", "b", "a", "c", "b"], expected=["a", "b", "c"]),
            _c([5, 5, 5], expected=[5]),
            _c([3, 1, 2], expected=[3, 1, 2]),
            _c(["x", "x", "y"], expected=["x", "y"]),
        ),
    ),
    "merge_intervals": TaskSpec(
        task_id="merge_intervals",
        entrypoint="merge_intervals",
        visible=(_c([[1, 3], [2, 6], [8, 10]], expected=[[1, 6], [8, 10]]),),
        hidden=(
            _c([[1, 4], [4, 5]], expected=[[1, 5]]),
            _c([[5, 6], [1, 2]], expected=[[1, 2], [5, 6]]),
            _c([[1, 10], [2, 3]], expected=[[1, 10]]),
            _c([], expected=[]),
        ),
    ),
    "balanced": TaskSpec(
        task_id="balanced",
        entrypoint="balanced",
        visible=(_c("()", expected=True), _c("(]", expected=False)),
        hidden=(
            _c("([{}])", expected=True),
            _c("((", expected=False),
            _c("", expected=True),
            _c("([)]", expected=False),
        ),
    ),
}

__all__ = [
    "SAMPLE_TASKS",
    "Case",
    "ExecResult",
    "ExecutionVerifier",
    "TaskSpec",
    "run_cases",
]
