"""代码任务上的策略进化 vs 随机搜索 vs 基线（真实测试通过率）。

    # 离线（模拟模型，仅验证流水线，不代表真实能力）
    python scripts/run_code_bench.py --simulate --budget 400

    # 真模型（密钥只从环境变量读取）
    python scripts/run_code_bench.py --provider deepseek --budget 400

注意：真模型必须关闭 JSON 模式，否则返回的不是代码。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.code_evolution import evolve_policy, held_out_report, random_search, split_tasks  # noqa: E402
from agh.codesolve import SolverPolicy  # noqa: E402
from agh.codetasks import TASKS  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="代码任务策略进化实验")
    p.add_argument("--simulate", action="store_true", help="用离线模拟模型")
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--model", default=None)
    p.add_argument("--api-key-env", default=None)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--budget", type=int, default=400, help="每种方法在 train 上可用的模型调用次数")
    p.add_argument(
        "--reward",
        choices=["absolute", "progress"],
        default="absolute",
        help="父代选择依据：绝对分数，还是相对上一步的进步（Oudeyer 学习进步假设）",
    )
    p.add_argument("--ladder", action="store_true", help="分级目标：先过公开用例，再看 hidden")
    p.add_argument("--held-out", type=int, default=4)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--p-correct", type=float, default=0.4, help="仅 --simulate")
    p.add_argument("--out", type=Path, default=ROOT / "runs" / "code" / "code-bench.json")
    args = p.parse_args()

    if args.simulate:
        from agh.simulated import SimulatedCoder

        complete = SimulatedCoder(p_correct=args.p_correct, seed=args.seed)
    else:
        from agh.providers import make_client

        complete = make_client(args.provider, model=args.model, api_key_env=args.api_key_env, json_mode=False)
        complete.max_tokens = args.max_tokens

    train, test = split_tasks(list(TASKS.values()), args.held_out, seed=args.seed)
    results = {
        "evolution": evolve_policy(
            train, complete, args.budget, seed=args.seed, reward=args.reward, ladder=args.ladder
        ),
        "random": random_search(
            train, complete, args.budget, seed=args.seed, reward=args.reward, ladder=args.ladder
        ),
    }
    report = held_out_report(results, SolverPolicy(), test, complete)
    report["mode"] = "simulated" if args.simulate else f"real:{args.provider}"
    if report["baseline"]["held_out_score"] >= 1.0:
        report["WARNING_CEILING"] = (
            "baseline 在 held-out 上全对：基准已触顶，进化/随机的差值没有意义，"
            "要么加更难的题，要么换更弱的模型"
        )
    errors = sum(report["call_errors"].values()) + report["baseline_call_errors"]
    if errors:
        report["WARNING_CALL_ERRORS"] = (
            f"{errors} 次模型调用失败：分数不可解释，先查密钥/余额/网络，别当成模型答错"
        )
    report["train_tasks"] = [t.spec.task_id for t in train]
    if args.simulate:
        report["WARNING"] = "模拟模型：数字只说明流水线能跑通，不代表任何真实模型"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
