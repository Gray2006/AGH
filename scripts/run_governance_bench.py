"""跑治理有效性对照实验，输出人读表 + JSON。

用法：
    python scripts/run_governance_bench.py --rounds 20 --out runs/governance.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agh.governance_bench import run_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    report = run_all(args.rounds)
    data = report.as_dict()

    for section in ("provenance", "ledger", "hashchain"):
        print(f"\n[{section}]")
        for arm in data[section]:
            print(
                f"  {arm['name']:<14} attempts={arm['attempts']:<4} "
                f"caught={arm['caught']:<4} rate={arm['catch_rate']:.2%} "
                f"false_rejects={arm['false_rejects']}"
            )

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
