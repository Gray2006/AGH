"""一条命令看完 AGH 能干什么。

不装 key、不写代码、不花 token：内置三次模拟调用，走一遍
「记录 → 标记问题 → 校验 → 重放 → 导出失败样本」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from .audit import AuditSession, export_failures


class _MockCall(TypedDict):
    model: str
    prompt: str
    response: str
    tokens: int
    flag: tuple[str, str] | None


# 内置样例：两次看起来正常，一次明显错误，用来演示 flag → 导出
_MOCK_CALLS: list[_MockCall] = [
    {
        "model": "mock/good-model",
        "prompt": "把 [3,1,2] 升序排列",
        "response": "```python\nsorted([3,1,2])\n```",
        "tokens": 42,
        "flag": None,
    },
    {
        "model": "mock/good-model",
        "prompt": "把 [] 升序排列",
        "response": "```python\nsorted([])\n```",
        "tokens": 18,
        "flag": None,
    },
    {
        "model": "mock/careless-model",
        "prompt": "把 [3,1,2] 降序排列",
        "response": "```python\nsorted([3,1,2])\n```",
        "tokens": 51,
        "flag": ("wrong", "要求降序，返回了升序"),
    },
]


@dataclass
class QuickstartReport:
    run_dir: Path
    log_path: Path
    failures_path: Path
    report_path: Path | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    replay: dict[str, Any] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "log": str(self.log_path),
            "failures": str(self.failures_path),
            "report": str(self.report_path) if self.report_path else None,
            "summary": self.summary,
            "replay": self.replay,
            "steps": self.steps,
        }


def run_quickstart(workdir: str | Path | None = None) -> QuickstartReport:
    run_dir = Path(workdir) if workdir is not None else Path.cwd() / "agh-quickstart"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.jsonl"
    if log_path.exists():
        log_path.unlink()

    steps: list[str] = []
    audit = AuditSession(log_path, label="quickstart")
    steps.append(f"1. 新建审计日志：{log_path}")

    with audit:
        for item in _MOCK_CALLS:
            call_id = audit.call(
                model=item["model"],
                prompt=item["prompt"],
                response=item["response"],
                tokens=item["tokens"],
            )
            steps.append(f"2. 记录一次调用：{call_id}（{item['model']}）")
            if item["flag"] is not None:
                reason, note = item["flag"]
                audit.flag(call_id, reason=reason, note=note)
                steps.append(f"3. 标记这次调用有问题：{reason} — {note}")

    summary = audit.summary()
    steps.append(
        f"4. 共 {summary['calls']} 次调用，{summary['tokens']} tokens，"
        f"{summary['flags']} 条标记"
    )

    audit.verify()
    steps.append("5. 哈希链校验通过（改一行就会被发现）")

    replay = audit.replay()
    steps.append(f"6. 重放：{replay['entries']} 条事件，链头 {replay['head'][:16]}")

    failures_path = run_dir / "failures.json"
    count = export_failures(log_path, failures_path)
    steps.append(f"7. 导出失败样本：{count} 条 → {failures_path}")

    report_path = run_dir / "report.html"
    from .ui import render_html

    report_path.write_text(render_html(log_path), encoding="utf-8")
    steps.append(f"8. 生成可视化报告：{report_path}")

    return QuickstartReport(
        run_dir=run_dir,
        log_path=log_path,
        failures_path=failures_path,
        report_path=report_path,
        summary=summary,
        replay=replay,
        steps=steps,
    )


def render_quickstart(report: QuickstartReport) -> str:
    lines = ["", "AGH quickstart — 30 秒看完审计链路", "=" * 48, ""]
    lines += report.steps
    lines += [
        "",
        "-" * 48,
        "接下来可以：",
        f"  agh audit summary --log {report.log_path}",
        f"  agh audit verify  --log {report.log_path}",
        f"  agh feedback      --log {report.log_path}",
        "",
        "接你自己的代码（三行）：",
        "  from agh import AuditSession",
        '  audit = AuditSession("run.jsonl")',
        '  audit.call(model="...", prompt=p, response=r)',
        "",
        f"用浏览器打开：{report.report_path}" if report.report_path else "",
        f"产物目录：{report.run_dir}",
    ]
    return "\n".join(lines)


__all__ = ["QuickstartReport", "render_quickstart", "run_quickstart"]
