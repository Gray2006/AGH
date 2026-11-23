"""跑 9 组消融：完整链路 + 8 个单点关闭，输出配对统计。

用法：
    python scripts/run_ablation.py --seeds 50 --out runs/g1/ablation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.ablation import run_ablation  # noqa: E402
from agh.arena import ArenaConfig  # noqa: E402
from agh.experiment import Arm  # noqa: E402
from agh.llm import RuleChild  # noqa: E402
from agh.pipeline import (  # noqa: E402
    PARENT_SIG,
    dissent_child,
    faithful_child,
    m0_skeleton,
    shallow_child,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="跑 AGH 消融套件")
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--resamples", type=int, default=2_000)
    parser.add_argument("--out", type=Path, default=ROOT / "runs" / "g1" / "ablation.json")
    args = parser.parse_args()

    cfg = ArenaConfig.from_frozen(ROOT / "config" / "frozen")
    arms = [
        Arm("faithful", RuleChild("faithful", faithful_child)),
        Arm("dissent", RuleChild("dissent", dissent_child)),
        Arm("shallow", RuleChild("shallow", shallow_child)),
    ]
    report = run_ablation(
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
