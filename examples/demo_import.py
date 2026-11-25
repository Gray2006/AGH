"""端到端演示：模拟一份 Langfuse 导出，导入、统计、生成报告。

跑法：
    python examples/demo_import.py

产物在 examples/out/ 下：
    langfuse.jsonl   模拟的 Langfuse 导出
    run.agh.jsonl    AGH 审计日志
    report.html      可视化报告
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agh.auditstats import compute_stats, render  # noqa: E402
from agh.importers import import_any  # noqa: E402
from agh.ui import render_html  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"

# 一份典型的 Langfuse generation 导出（字段按官方 blob export）
SAMPLE = [
    {
        "type": "generation",
        "trace_id": "trace-001",
        "input": "把 [3,1,2] 升序排列，只返回结果",
        "output": "[1,2,3]",
        "model": "gpt-x",
        "usage": {"input": 18, "output": 6},
    },
    {
        "type": "generation",
        "trace_id": "trace-002",
        "input": "把 [3,1,2] 降序排列，只返回结果",
        "output": "[1,2,3]",
        "model": "gpt-x",
        "usage": {"input": 18, "output": 6},
    },
    {
        "type": "generation",
        "trace_id": "trace-003",
        "input": "解释什么是哈希链",
        "output": "每条记录包含上一条的哈希，改动任意一条都会让后续哈希对不上。",
        "model": "gpt-y",
        "usage": {"input": 9, "output": 28},
    },
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    src = OUT / "langfuse.jsonl"
    src.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in SAMPLE) + "\n",
        encoding="utf-8",
    )
    print(f"1. 写出模拟导出：{src}")

    result = import_any(src, OUT / "run.agh.jsonl")
    print(
        f"2. 导入：格式={result.detected_format} 成功={result.imported} 跳过={result.skipped}"
    )

    stats = compute_stats(OUT / "run.agh.jsonl")
    print("3. 统计：")
    for line in render(stats).splitlines():
        print(f"   {line}")

    html_path = OUT / "report.html"
    html_path.write_text(render_html(OUT / "run.agh.jsonl"), encoding="utf-8")
    print(f"4. 报告：{html_path}（用浏览器打开）")

    print("\n下一步可以试：")
    print(f"   agh audit verify --log {OUT / 'run.agh.jsonl'}")
    print(f"   agh feedback --log {OUT / 'run.agh.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
