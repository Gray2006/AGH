"""真模型跨基准实验：在 N 个生成骨架上一一重构，与同骨架的规则子级对比。

    python scripts/run_llm_bench.py --provider command-code --benchmarks 10

同时把候选重构落盘，供验证器校准复用（不重复调用模型）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.arena import ArenaConfig, hard_filter, score_candidate  # noqa: E402
from agh.benchmarks import generate_benchmarks  # noqa: E402
from agh.evalstats import paired_bootstrap_ci  # noqa: E402
from agh.evolution import strategy_child  # noqa: E402
from agh.evolution_sharded import seed_for  # noqa: E402
from agh.llm import ChildOutputError, LlmChild  # noqa: E402
from agh.providers import make_client  # noqa: E402
from agh.verifier import StructuralVerifier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="真模型跨基准实验")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--benchmarks", type=int, default=10)
    parser.add_argument("--bench-seed", type=int, default=0)
    parser.add_argument("--min-nodes", type=int, default=5)
    parser.add_argument("--max-nodes", type=int, default=5)
    parser.add_argument("--extra-edges", type=int, default=2)
    parser.add_argument("--required-ratio", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "llm-bench.json")
    parser.add_argument("--candidates-out", type=Path, default=ROOT / "runs" / "g1" / "llm-bench-candidates.json")
    args = parser.parse_args()

    cfg = ArenaConfig.from_frozen(ROOT / "config" / "frozen")
    verifier = StructuralVerifier()
    client = make_client(args.provider, model=args.model, api_key_env=args.api_key_env)
    client.max_tokens = args.max_tokens
    benches = generate_benchmarks(
        args.benchmarks,
        seed=args.bench_seed,
        min_nodes=args.min_nodes,
        max_nodes=args.max_nodes,
        extra_edges=args.extra_edges,
        required_ratio=args.required_ratio,
    )

    llm_scores: list[float] = []
    rule_scores: list[float] = []
    per_bench: list[dict] = []
    candidates: list[dict] = []
    for bench in benches:
        sk = bench.skeleton
        child = LlmChild(
            name="llm-bench",
            complete=client,
            skeleton=sk,
            parent_features=list(bench.parent.features),
        )
        try:
            recon = child.reconstruct(f"ct-{sk.skeleton_id}")
        except ChildOutputError as exc:
            per_bench.append({"skeleton": sk.skeleton_id, "error": str(exc)})
            continue
        if not hard_filter(recon, sk).passed:
            per_bench.append({"skeleton": sk.skeleton_id, "error": "hard_filter"})
            continue
        vscore = verifier.score(recon, sk)
        llm_score = score_candidate(
            recon, sk, cfg, verifier_score=vscore, parent_signature=bench.parent
        ).score
        rule_recon = strategy_child(seed_for(bench), sk)(f"ct-{sk.skeleton_id}")
        rule_score = score_candidate(
            rule_recon,
            sk,
            cfg,
            verifier_score=verifier.score(rule_recon, sk),
            parent_signature=bench.parent,
        ).score
        llm_scores.append(llm_score)
        rule_scores.append(rule_score)
        per_bench.append(
            {
                "skeleton": sk.skeleton_id,
                "llm": round(llm_score, 5),
                "rule": round(rule_score, 5),
                "verifier": round(vscore, 3),
            }
        )
        candidates.append(
            {
                "skeleton": sk.model_dump(mode="json"),
                "reconstruction": recon.model_dump(mode="json"),
            }
        )

    deltas = [a - b for a, b in zip(llm_scores, rule_scores, strict=False)]
    report = {
        "provider": args.provider,
        "model": client.model,
        "benchmarks": len(benches),
        "valid": len(llm_scores),
        "llm_mean": round(mean(llm_scores), 5) if llm_scores else 0.0,
        "rule_mean": round(mean(rule_scores), 5) if rule_scores else 0.0,
        "delta": (
            {
                "mean": round(paired_bootstrap_ci(deltas, resamples=2000, seed=0).mean, 5),
                "lo": round(paired_bootstrap_ci(deltas, resamples=2000, seed=0).lo, 5),
                "hi": round(paired_bootstrap_ci(deltas, resamples=2000, seed=0).hi, 5),
                "n": len(deltas),
            }
            if len(deltas) >= 2
            else None
        ),
        "per_benchmark": per_bench,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.candidates_out.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告: {args.out}\n候选: {args.candidates_out}")
    return 0 if llm_scores else 1


if __name__ == "__main__":
    raise SystemExit(main())
