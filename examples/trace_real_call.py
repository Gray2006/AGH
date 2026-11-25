"""端到端：用真实模型跑一次调用，全程记录进审计日志。

需要环境变量 `COMMAND_CODE_API_KEY`（或换 provider）。没有 key 时只跑离线部分。

跑法：
    python examples/trace_real_call.py

产物在 examples/out/live/：
    run.jsonl        审计日志（含真实调用）
    report.html      可视化报告
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agh.audit import AuditSession  # noqa: E402
from agh.auditstats import compute_stats, render  # noqa: E402
from agh.ui import render_html  # noqa: E402

OUT = Path(__file__).resolve().parent / "out" / "live"

PROMPTS = [
    "用一句话解释什么是哈希链。",
    "把 [3,1,2] 降序排列，只返回结果。",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    log_path = OUT / "run.jsonl"
    if log_path.exists():
        log_path.unlink()

    key = os.environ.get("COMMAND_CODE_API_KEY", "")
    if not key:
        print("没有 COMMAND_CODE_API_KEY，跳过真实调用（这不算失败）")
        return 0

    from agh.providers import make_client

    client = make_client(
        "command-code",
        model="deepseek/deepseek-v4.1-flash",
        api_key_env="COMMAND_CODE_API_KEY",
        json_mode=False,
    )

    audit = AuditSession(log_path, label="live-demo")
    with audit:
        for prompt in PROMPTS:
            try:
                reply = client(prompt)
            except Exception as exc:  # 调用失败也要记录，不能静默跳过
                audit.note("llm.error", prompt=prompt, error=type(exc).__name__)
                print(f"调用失败：{type(exc).__name__}")
                continue
            usage = getattr(client, "last_usage", None) or {}
            tokens = int(usage.get("total_tokens") or 0)
            call_id = audit.call(
                model="deepseek/deepseek-v4.1-flash",
                prompt=prompt,
                response=reply,
                tokens=tokens,
            )
            print(f"记录 {call_id}：{reply.strip()[:60]}")

    audit.verify()
    print("哈希链校验通过")

    stats = compute_stats(log_path)
    print(render(stats))

    html = OUT / "report.html"
    html.write_text(render_html(log_path), encoding="utf-8")
    print(f"报告：{html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
