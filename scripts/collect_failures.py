"""从真实模型运行中收集失败样本，写成可提交的任务族 fixture。

用法：
    python scripts/collect_failures.py --provider command-code --attempts 2 \
        --out tests/fixtures/real_failures.json
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agh.arena import ArenaConfig  # noqa: E402
from agh.benchmarks import generate_benchmarks  # noqa: E402
from agh.evolution import evaluate_strategy  # noqa: E402
from agh.evolution_llm import LlmStrategyMutator  # noqa: E402
from agh.evolution_sharded import seed_for  # noqa: E402
from agh.failures import FailureCase, dump_failures  # noqa: E402
from agh.providers import make_client  # noqa: E402
from agh.verifier import StructuralVerifier  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="command-code")
    ap.add_argument("--model", default=None)
    ap.add_argument("--api-key-env", default="COMMAND_CODE_API_KEY")
    ap.add_argument("--benchmarks", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--max-cases", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=0.02)
    ap.add_argument("--out", default="tests/fixtures/real_failures.json")
    args = ap.parse_args()

    cfg = ArenaConfig.from_frozen(ROOT / "config" / "frozen")
    verifier = StructuralVerifier()
    client = make_client(args.provider, model=args.model, api_key_env=args.api_key_env)
    tokens = 0
    cases: list[FailureCase] = []

    for bench in generate_benchmarks(args.benchmarks, seed=args.seed):
        nodes = sorted(bench.skeleton.nodes)
        features = sorted(f"{a}-{b}" for a, b in bench.skeleton.edges)
        seed = seed_for(bench, rng=random.Random(f"0:{bench.skeleton.skeleton_id}"))
        seed_fit = evaluate_strategy(seed, [bench], cfg, verifier=verifier).fitness
        mutator = LlmStrategyMutator(features, nodes, complete=client)
        for attempt in range(args.attempts):
            candidate = mutator.mutate(seed, random.Random(attempt), f"llm-{attempt}")
            tokens += int((client.last_usage or {}).get("total_tokens", 0) or 0)
            fit = evaluate_strategy(candidate, [bench], cfg, verifier=verifier).fitness
            if fit < seed_fit - args.threshold:
                cases.append(
                    FailureCase(
                        case_id=f"{bench.skeleton.skeleton_id}-a{attempt}",
                        skeleton=bench.skeleton,
                        seed=candidate,
                        failed_score=fit,
                        note=f"seed={seed_fit:.4f} llm={fit:.4f}",
                    )
                )
                print(f"FAIL {bench.skeleton.skeleton_id} attempt {attempt}: {seed_fit:.4f} -> {fit:.4f}")
    cases = cases[: args.max_cases]
    dump_failures(cases, ROOT / args.out)
    print(f"wrote {len(cases)} cases to {args.out}, tokens={tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
