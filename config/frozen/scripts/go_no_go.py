"""Go/No-Go 判定脚本（D11）。放在冻结层内，改动会破坏锚点。

用法：
    python scripts/go_no_go.py --results results.json --anchor ../anchor.json

results.json 形如 {"G0-ledger": 0, "l1_replay_bit_exact": true, ...}
只接受冻结的 phase_gates.json 里的指标，不接受命令行改判。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent
sys.path.insert(0, str(FROZEN.parent.parent))

from agh.frozen import FrozenLayer, load_json  # noqa: E402


def judge(metric: str, rule: str, target: float, value: float) -> bool:
    if rule == "eq":
        return value == target
    if rule == "gt":
        return value > target
    if rule == "lt":
        return value < target
    raise ValueError(f"未知规则: {rule}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--anchor", default=str(FROZEN.parent / "anchor.json"))
    args = parser.parse_args(argv)

    gates = load_json(FROZEN, "phase_gates.json")
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))

    anchor_path = Path(args.anchor)
    if anchor_path.exists():
        # 锚点校验需要密钥环，这里只做结构一致性提示；签名校验由 CI 用密钥跑
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        current = FrozenLayer(FROZEN).manifest()
        if anchor.get("manifest") != current:
            print("FAIL 冻结层哈希与锚点不一致，拒绝判定")
            return 2

    failures: list[str] = []
    for gate in gates["gates"]:
        metric = gate["metric"]
        if metric not in results:
            if gate.get("blocking"):
                failures.append(f"{gate['id']}: 缺少指标 {metric}")
            continue
        ok = judge(metric, gate["rule"], gate["target"], results[metric])
        print(("PASS " if ok else "FAIL ") + f"{gate['id']} ({metric}={results[metric]})")
        if not ok and gate.get("blocking"):
            failures.append(gate["id"])

    if failures:
        print("NO-GO: " + ", ".join(failures))
        return 1
    print("GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
