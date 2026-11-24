"""验证器校准：结构验证器 vs 模型裁判，在真实候选上比对一致度。

    python scripts/run_verifier_calibration.py --provider command-code

读取 run_llm_bench.py 落盘的候选，不重新生成。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.calibration import evaluate  # noqa: E402
from agh.contracts import GestaltReconstruction, Skeleton  # noqa: E402
from agh.providers import make_client  # noqa: E402
from agh.verifier import LlmJudgeVerifier, StructuralVerifier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="校准结构验证器与模型裁判")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--candidates", type=Path, default=ROOT / "runs" / "g1" / "llm-bench-candidates.json")
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "verifier-calibration.json")
    args = parser.parse_args()

    items = json.loads(args.candidates.read_text(encoding="utf-8"))
    client = make_client(args.provider, model=args.model, api_key_env=args.api_key_env)
    structural = StructuralVerifier()
    judge = LlmJudgeVerifier(complete=client)

    structural_scores: list[float] = []
    judge_scores: list[float] = []
    per_item: list[dict] = []
    for index, item in enumerate(items):
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        s = structural.score(recon, skeleton)
        j = judge.score(recon, skeleton)
        structural_scores.append(s)
        judge_scores.append(j)
        per_item.append({"index": index, "skeleton": skeleton.skeleton_id, "structural": s, "judge": j})

    report = {
        "n": len(items),
        "calibration": evaluate(structural_scores, judge_scores).as_dict(),
        "items": per_item,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["calibration"], ensure_ascii=False, indent=2))
    print(f"\n报告: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
