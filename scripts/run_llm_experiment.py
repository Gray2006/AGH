"""真模型 G1 采样实验：同一契约下让模型重复重构，统计通过率与分数分布。

    python scripts/run_llm_experiment.py --provider command-code --samples 8

与规则子级的 experiment 不同，这里不做多臂对照，只回答一个问题：
真模型在契约约束下，产出合格重构的比例与质量分布是什么。
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
from agh.evalstats import paired_bootstrap_ci  # noqa: E402
from agh.llm import ChildOutputError, LlmChild  # noqa: E402
from agh.pipeline import PARENT_SIG, faithful_child, m0_skeleton  # noqa: E402
from agh.providers import make_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="真模型契约通过率与分数分布")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "llm-experiment.json")
    args = parser.parse_args()

    cfg = ArenaConfig.from_frozen(ROOT / "config" / "frozen")
    skeleton = m0_skeleton()
    client = make_client(
        args.provider, model=args.model, base_url=args.base_url, api_key_env=args.api_key_env
    )
    child = LlmChild(
        name="llm-child",
        complete=client,
        skeleton=skeleton,
        parent_features=PARENT_SIG.features,
    )

    scores: list[float] = []
    errors: list[dict] = []
    for index in range(args.samples):
        try:
            recon = child.reconstruct(f"ct-llm-{index}")
        except ChildOutputError as exc:
            errors.append({"sample": index, "error": str(exc), "details": exc.errors[:3]})
            continue
        filt = hard_filter(recon, skeleton)
        if not filt.passed:
            errors.append({"sample": index, "error": "hard_filter", "details": filt.reasons})
            continue
        breakdown = score_candidate(
            recon, skeleton, cfg, verifier_score=None, parent_signature=PARENT_SIG
        )
        scores.append(breakdown.score)

    rule_score = score_candidate(
        faithful_child("ct-rule"), skeleton, cfg, verifier_score=None, parent_signature=PARENT_SIG
    ).score
    deltas = [s - rule_score for s in scores]
    report = {
        "provider": args.provider,
        "model": client.model,
        "samples": args.samples,
        "valid": len(scores),
        "success_rate": round(len(scores) / args.samples, 3) if args.samples else 0.0,
        "mean_score": round(mean(scores), 5) if scores else 0.0,
        "min_score": round(min(scores), 5) if scores else 0.0,
        "max_score": round(max(scores), 5) if scores else 0.0,
        "rule_baseline": round(rule_score, 5),
        "delta_vs_rule": (
            {
                "mean": round(paired_bootstrap_ci(deltas, resamples=2000, seed=0).mean, 5),
                "lo": round(paired_bootstrap_ci(deltas, resamples=2000, seed=0).lo, 5),
                "hi": round(paired_bootstrap_ci(deltas, resamples=2000, seed=0).hi, 5),
                "n": len(deltas),
            }
            if len(deltas) >= 2
            else None
        ),
        "errors": errors,
    }
    target = args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告: {target}")
    return 0 if scores else 1


if __name__ == "__main__":
    raise SystemExit(main())
