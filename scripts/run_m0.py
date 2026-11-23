"""跑 M0 垂直切片，打印报告并落盘 runs/m0/。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.crypto import KeyRing  # noqa: E402
from agh.frozen import FrozenLayer  # noqa: E402
from agh.pipeline import DEV_KID, DEV_SECRET, run_m0  # noqa: E402


def main() -> int:
    frozen = ROOT / "config" / "frozen"
    anchor = ROOT / "config" / "anchor.json"
    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    layer = FrozenLayer(frozen)
    if anchor.exists():
        layer.verify(anchor, keyring)
        print(f"锚点校验通过: {anchor}")
    else:
        layer.write_anchor(anchor, keyring, DEV_KID)
        print(f"锚点已生成: {anchor}")

    run_dir = ROOT / "runs" / "m0"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    report = run_m0(frozen_root=frozen, run_dir=run_dir)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n事件日志: {run_dir / 'events.jsonl'}")
    print(f"报告: {run_dir / 'report.json'}")
    return 0 if report.l1_bit_exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
