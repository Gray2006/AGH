"""命令行入口：`python -m agh` 跑 M0 垂直切片。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .crypto import KeyRing
from .frozen import FrozenLayer
from .pipeline import DEV_KID, DEV_SECRET, run_m0


def repo_root() -> Path:
    """源码仓库根目录（含 config/frozen）。"""
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agh", description="跑 AGH M0 垂直切片并输出报告"
    )
    parser.add_argument(
        "--root", type=Path, default=None, help="含 config/frozen 的目录，默认仓库根"
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="输出目录，默认 <root>/runs/m0"
    )
    parser.add_argument(
        "--refresh-anchor",
        action="store_true",
        help="冻结层改动后重建锚点（会重新签名当前目录）",
    )
    args = parser.parse_args(argv)

    root = (args.root or repo_root()).resolve()
    frozen = root / "config" / "frozen"
    if not frozen.is_dir():
        parser.error(f"找不到冻结配置目录: {frozen}")
    anchor = root / "config" / "anchor.json"
    run_dir = (args.out or root / "runs" / "m0").resolve()

    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    layer = FrozenLayer(frozen)
    if anchor.exists() and not args.refresh_anchor:
        layer.verify(anchor, keyring)
        print(f"锚点校验通过: {anchor}")
    else:
        layer.write_anchor(anchor, keyring, DEV_KID)
        print(f"锚点已{'重建' if anchor.exists() else '生成'}: {anchor}")

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    report = run_m0(frozen_root=frozen, run_dir=run_dir)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n事件日志: {run_dir / 'events.jsonl'}")
    print(f"报告: {run_dir / 'report.json'}")
    return 0 if report.l1_bit_exact else 1
