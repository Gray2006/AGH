"""环境自检：装完之后跑一遍，看哪一项没准备好。

不读凭证内容，只报「有没有」。
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "version": __version__,
            "checks": [c.as_dict() for c in self.checks],
        }


def _check_python(report: DoctorReport) -> None:
    major, minor = sys.version_info[:2]
    report.add(
        "python>=3.11",
        (major, minor) >= (3, 11),
        f"{platform.python_version()} ({sys.executable})",
    )


def _check_writable(report: DoctorReport) -> None:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "agh-probe.txt"
            probe.write_text("ok", encoding="utf-8")
        report.add("temp writable", True, tempfile.gettempdir())
    except OSError as exc:
        report.add("temp writable", False, str(exc))


def _check_frozen(report: DoctorReport) -> None:
    root = Path(__file__).resolve().parents[1] / "config" / "frozen"
    exists = root.is_dir()
    report.add("frozen config", exists, str(root) if exists else f"缺失：{root}")


def _check_key_env(report: DoctorReport) -> None:
    names = (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "COMMAND_CODE_API_KEY",
        "ZHIPU_API_KEY",
    )
    present = [n for n in names if os.environ.get(n)]
    # 没有 key 不算失败：审计、校验、重放、报告都不需要它，只有跑模型才需要
    report.add(
        "model api key",
        True,
        f"已配置：{', '.join(present)}"
        if present
        else "没有可用 key（只影响跑模型，不影响审计与校验）",
    )


def _check_optional_deps(report: DoctorReport) -> None:
    try:
        import nats  # noqa: F401

        report.add("nats-py", True, "已安装")
    except ImportError:
        report.add("nats-py", True, "未安装（可选，仅 NATS 联调需要）")


def _check_git(report: DoctorReport) -> None:
    path = shutil.which("git")
    report.add("git", path is not None, path or "未找到（仅影响锚定到 git tag）")


def run_doctor() -> DoctorReport:
    report = DoctorReport()
    _check_python(report)
    _check_writable(report)
    _check_frozen(report)
    _check_key_env(report)
    _check_optional_deps(report)
    _check_git(report)
    return report


def render(report: DoctorReport) -> str:
    lines = [f"AGH {__version__} 环境自检", ""]
    for check in report.checks:
        mark = "OK  " if check.ok else "FAIL"
        lines.append(f"[{mark}] {check.name}: {check.detail}")
    lines.append("")
    lines.append("全部通过。" if report.ok else "有项目未通过，见上。")
    return "\n".join(lines)


__all__ = ["Check", "DoctorReport", "render", "run_doctor"]
