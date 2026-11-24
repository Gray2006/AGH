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
    env = dict(os.environ)
    # Windows 控制台默认 GBK，twine 的 rich 进度条会因 • 字符崩掉
    env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.run(cmd, cwd=ROOT, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只构建并校验")
    parser.add_argument("--upload", action="store_true", help="构建并上传到 PyPI")
    parser.add_argument(
        "--token-file",
        default=None,
        help="从文件读 PyPI token（推荐：token 不进命令行、不进历史）",
    )
    args = parser.parse_args()
    if not (args.check or args.upload):
        parser.error("至少给 --check 或 --upload")

    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    run([sys.executable, "-m", "build"])
    artifacts = sorted(str(p) for p in dist.iterdir() if p.is_file())
    if not artifacts:
        print("dist/ 为空，构建失败", file=sys.stderr)
        return 1
    run([sys.executable, "-m", "twine", "check", *artifacts])
    print("构建与校验通过：dist/")

    if args.upload:
        if args.token_file:
            token = Path(args.token_file).read_text(encoding="utf-8").strip()
            if not token.startswith("pypi-"):
                print(f"token 文件格式不对（应以 pypi- 开头）：{args.token_file}", file=sys.stderr)
                return 2
            os.environ["TWINE_PASSWORD"] = token
            print(f"已从 {args.token_file} 读取 token（不回显）")
        if not os.environ.get("TWINE_PASSWORD"):
            print("缺少 TWINE_PASSWORD（PyPI API token，以 pypi- 开头）", file=sys.stderr)
            return 2
        os.environ.setdefault("TWINE_USERNAME", "__token__")
        run([sys.executable, "-m", "twine", "upload", *artifacts])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
