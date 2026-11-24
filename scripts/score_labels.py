"""计算人工标注与结构验证器的一致度。

    python scripts/score_labels.py --labels runs/g1/label-template.json

答案模板里 label 必须全部填成 0 或 1；缺项会报出来。
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
from agh.verifier import StructuralVerifier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="人工标注 vs 结构验证器")
    parser.add_argument("--labels", type=Path, default=ROOT / "runs" / "g1" / "label-template.json")
    parser.add_argument("--candidates", type=Path, default=ROOT / "runs" / "g1" / "llm-bench-candidates.json")
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "human-calibration.json")
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    items = json.loads(args.candidates.read_text(encoding="utf-8"))
    missing = [row["index"] for row in labels if row.get("label") not in (0, 1)]
    if missing:
        print(f"还有 {len(missing)} 题没填：{missing}")
        return 1

    verifier = StructuralVerifier()
    human: list[float] = []
    machine: list[float] = []
    for row in labels:
        item = items[row["index"]]
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        human.append(float(row["label"]))
        machine.append(verifier.score(recon, skeleton))

    report = evaluate(machine, human)
    payload = {"n": len(human), **report.as_dict(), "human": human, "machine": [round(x, 3) for x in machine]}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n报告: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
