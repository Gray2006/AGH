"""跑代码任务的竞技场：治理层 + 真实测试信号。

    python scripts/run_code_arena.py --task dedupe --simulate
    python scripts/run_code_arena.py --task dedupe --provider deepseek --samples 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agh.code_arena import run_code_arena
from agh.codesolve import SolverPolicy, build_prompt, extract_code
from agh.codetasks import TASKS

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="dedupe", choices=sorted(TASKS))
    parser.add_argument("--samples", type=int, default=1, help="每个子级采样几个候选")
    parser.add_argument("--children", type=int, default=2, help="几个子级（每个用不同策略）")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    task = TASKS[args.task]

    if args.simulate:
        from agh.simulated import SimulatedCoder

        coder = SimulatedCoder(seed=0)

        def complete(prompt: str) -> str:
            return coder(prompt)

    else:
        from agh.providers import make_client

        client = make_client(
            args.provider, model=args.model, api_key_env=args.api_key_env, json_mode=False
        )
        client.max_tokens = args.max_tokens
        complete = client

    policies = [
        SolverPolicy(n_samples=args.samples),
        SolverPolicy(n_samples=1, select="visible_best"),
        SolverPolicy(n_samples=args.samples, hint="edge_cases"),
    ][: max(1, args.children)]

    solvers = []
    for i, policy in enumerate(policies):
        def make(policy=policy, i=i):
            def solve(t):
                # 一次「策略」= 采样 n 个候选，选 visible 最高的那个
                best, best_vis = "", -1.0
                for k in range(policy.n_samples):
                    code = extract_code(complete(build_prompt(t, policy, k)))
                    from agh.execverify import run_cases

                    vis = run_cases(code, t.spec, t.spec.visible).score
                    if vis > best_vis:
                        best, best_vis = code, vis
                return best

            return solve

        solvers.append((f"child-{i}", make()))

    report = run_code_arena(task, solvers, run_dir=ROOT / "runs" / "code-arena" / args.task,
                            frozen_root=ROOT / "config" / "frozen")
    data = report.as_dict()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
