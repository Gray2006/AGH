"""跑 G1 竞技场实验：多子级 × 多随机种子，输出带统计结论的报告。

用法：
    python scripts/run_experiment.py --seeds 100 --out runs/g1/experiment.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.arena import ArenaConfig  # noqa: E402
from agh.experiment import Arm, run_experiment  # noqa: E402
from agh.llm import RuleChild  # noqa: E402
from agh.pipeline import (  # noqa: E402
    PARENT_SIG,
    dissent_child,
    faithful_child,
    m0_skeleton,
    shallow_child,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="跑 AGH G1 竞技场实验")
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--resamples", type=int, default=2_000)
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "experiment.json")
    args = parser.parse_args()

    frozen = ROOT / "config" / "frozen"
    cfg = ArenaConfig.from_frozen(frozen)
    arms = [
        Arm("faithful", RuleChild("faithful", faithful_child)),
        Arm("dissent", RuleChild("dissent", dissent_child)),
        Arm("shallow", RuleChild("shallow", shallow_child)),
    ]
    report = run_experiment(
        arms,
        m0_skeleton(),
        cfg,
        parent_features=PARENT_SIG.features,
        seeds=range(args.seeds),
        resamples=args.resamples,
    )
    target = report.write(args.out)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n报告: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
