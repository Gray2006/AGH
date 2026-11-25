"""新用户旅程冒烟：从零到「看完报告」，走一遍所有日常命令。

和 CI 的 package job 不同，这里按真实使用顺序串联，并检查每步产物。
跑法：python scripts/smoke_journey.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], cwd: Path) -> tuple[int, str, float]:
    start = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "agh", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip(), time.time() - start


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agh-journey-") as tmp:
        work = Path(tmp)

        code, out, secs = run(["quickstart", "--dir", "qs"], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] quickstart {secs:.2f}s")
        if code != 0:
            failures.append(f"quickstart: {out[:200]}")
        log = work / "qs" / "run.jsonl"
        if not log.exists():
            failures.append("quickstart 没产出 run.jsonl")

        code, out, secs = run(["audit", "verify", "--log", str(log)], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] audit verify {secs:.2f}s")
        if code != 0:
            failures.append(f"verify: {out[:200]}")

        code, out, secs = run(["audit", "summary", "--log", str(log)], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] audit summary {secs:.2f}s")
        if code != 0:
            failures.append(f"summary: {out[:200]}")

        code, out, secs = run(["audit-stats", "--log", str(log), "--json"], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] audit-stats {secs:.2f}s")
        if code == 0:
            try:
                data = json.loads(out)
                if data["total_calls"] < 1:
                    failures.append("stats 显示 0 次调用")
            except json.JSONDecodeError:
                failures.append("audit-stats --json 输出不是合法 JSON")
        else:
            failures.append(f"stats: {out[:200]}")

        code, out, secs = run(["audit-timeline", "--log", str(log), "--limit", "3"], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] audit-timeline {secs:.2f}s")
        if code != 0:
            failures.append(f"timeline: {out[:200]}")

        code, out, secs = run(["ui", "--log", str(log), "--out", "r.html", "--no-open"], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] ui {secs:.2f}s")
        html = work / "r.html"
        if not html.exists() or html.stat().st_size < 1000:
            failures.append("ui 没产出有内容的 HTML")

        code, out, secs = run(["audit-export", "--log", str(log), "--out", "c.csv"], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] audit-export {secs:.2f}s")
        if not (work / "c.csv").exists():
            failures.append("audit-export 没产出 CSV")

        code, out, secs = run(["feedback", "--log", str(log), "--out", "fb.md"], work)
        print(f"[{'ok' if code == 0 else 'FAIL'}] feedback {secs:.2f}s")
        if not (work / "fb.md").exists():
            failures.append("feedback 没产出 markdown")

        code, out, secs = run(["doctor", "--json"], work)
        print(f"[{'ok' if code in (0, 1) else 'FAIL'}] doctor {secs:.2f}s")
        try:
            json.loads(out)
        except json.JSONDecodeError:
            failures.append("doctor --json 输出不是合法 JSON")

    print()
    if failures:
        print(f"失败 {len(failures)} 项：")
        for item in failures:
            print(" -", item)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
