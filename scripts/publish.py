"""构建并（可选）发布到 PyPI。

PyPI 上 `agh` 这个名字已被别的项目占用（Agent Guidance Hub），
所以发行名是 `agh-gestalt`，import 名仍是 `agh`，CLI 仍是 `agh`。

用法：
    python scripts/publish.py --check        # 只构建 + twine check，不发布
    python scripts/publish.py --upload       # 构建并上传（需要 TWINE_PASSWORD）
    TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-... python scripts/publish.py --upload
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只构建并校验")
    parser.add_argument("--upload", action="store_true", help="构建并上传到 PyPI")
    args = parser.parse_args()
    if not (args.check or args.upload):
        parser.error("至少给 --check 或 --upload")

    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    run([sys.executable, "-m", "build"])
    run([sys.executable, "-m", "twine", "check", "dist/*"])
    print("构建与校验通过：dist/")

    if args.upload:
        if not os.environ.get("TWINE_PASSWORD"):
            print("缺少 TWINE_PASSWORD（PyPI API token，以 pypi- 开头）", file=sys.stderr)
            return 2
        run([sys.executable, "-m", "twine", "upload", "dist/*"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
