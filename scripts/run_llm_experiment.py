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
from agh.verifier import make_verifier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="真模型契约通过率与分数分布")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--include-reference", action="store_true", help="提示里附一个参考重构（消融）")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--with-hints", action="store_true", help="提示里给特征命名约定（结构标签）")
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--verifier", choices=["structural", "coverage"], default=None)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "llm-experiment.json")
    args = parser.parse_args()

    cfg = ArenaConfig.from_frozen(ROOT / "config" / "frozen")
    skeleton = m0_skeleton()
    client = make_client(
        args.provider, model=args.model, base_url=args.base_url, api_key_env=args.api_key_env
    )
    client.max_tokens = args.max_tokens
    if args.temperature is not None:
        client.temperature = args.temperature
    reference = None
    if args.include_reference:
        reference = faithful_child("ct-reference").model_dump(mode="json")
    child = LlmChild(
        name="llm-child",
        complete=client,
        skeleton=skeleton,
        parent_features=PARENT_SIG.features,
        reference=reference,
        with_hints=args.with_hints,
    )

    verifier = make_verifier(args.verifier) if args.verifier else None

    def run_one(index: int) -> dict:
        local_client = client
        local_child = child
        if args.parallel > 1:
            local_client = make_client(
                args.provider, model=args.model, api_key_env=args.api_key_env
            )
            local_client.max_tokens = args.max_tokens
            if args.temperature is not None:
                local_client.temperature = args.temperature
            local_child = LlmChild(
                name="llm-child",
                complete=local_client,
                skeleton=skeleton,
                parent_features=PARENT_SIG.features,
                reference=reference,
                with_hints=args.with_hints,
            )
        try:
            recon = local_child.reconstruct(f"ct-llm-{index}")
        except ChildOutputError as exc:
            return {"index": index, "error": str(exc), "details": exc.errors[:3], "usage": None}
        filt = hard_filter(recon, skeleton)
        if not filt.passed:
            return {"index": index, "error": "hard_filter", "details": filt.reasons, "usage": None}
        verifier_score = verifier.score(recon, skeleton) if verifier else None
        breakdown = score_candidate(
            recon, skeleton, cfg, verifier_score=verifier_score, parent_signature=PARENT_SIG
        )
        return {"index": index, "score": breakdown.score, "usage": local_client.last_usage}

    if args.parallel > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            results = list(pool.map(run_one, range(args.samples)))
    else:
        results = [run_one(i) for i in range(args.samples)]

    scores: list[float] = []
    errors: list[dict] = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for result in results:
        if "error" in result:
            errors.append(
                {"sample": result["index"], "error": result["error"], "details": result["details"]}
            )
            continue
        scores.append(result["score"])
        if result["usage"]:
            for key in usage_total:
                usage_total[key] += int(result["usage"].get(key, 0) or 0)

    rule_recon = faithful_child("ct-rule")
    rule_score = score_candidate(
        rule_recon,
        skeleton,
        cfg,
        verifier_score=verifier.score(rule_recon, skeleton) if verifier else None,
        parent_signature=PARENT_SIG,
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
        "include_reference": bool(args.include_reference),
        "temperature": client.temperature,
        "with_hints": bool(args.with_hints),
        "verifier": args.verifier,
        "scores": [round(x, 5) for x in scores],
        "usage": usage_total,
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
