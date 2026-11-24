"""发布：版本校验 → 可选上传 PyPI → 跑 M0 → 锚定到 git tag。

用法：
    python scripts/release.py --check          # 只校验版本与工作区
    python scripts/release.py                  # 跑 M0 并锚定（本地 tag）
    python scripts/release.py --push           # 锚定并把 tag 推到 origin
    python scripts/release.py --upload --token-file .pypi_token
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agh.anchoring import GitTagStore
from agh.release import (
    ReleaseError,
    anchor_release,
    anchor_summary,
    read_version,
    require_clean_tree,
    verify_release,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验版本与工作区")
    parser.add_argument("--upload", action="store_true", help="先上传到 PyPI")
    parser.add_argument("--token-file", default=None)
    parser.add_argument("--push", action="store_true", help="把锚点 tag 推到 origin")
    parser.add_argument("--verify", action="store_true", help="只校验上一次锚定")
    args = parser.parse_args()

    try:
        version = read_version(ROOT)
        print(f"版本：{version}")
        if args.verify:
            store = GitTagStore(ROOT)
            print(verify_release(ROOT, version=version, git_store=store))
            return 0
        if args.check:
            require_clean_tree(ROOT)
            print("工作区干净，版本一致")
            return 0
        require_clean_tree(ROOT)
    except ReleaseError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1

    if args.upload:
        cmd = [sys.executable, "scripts/publish.py", "--upload"]
        if args.token_file:
            cmd += ["--token-file", args.token_file]
        subprocess.run(cmd, cwd=ROOT, check=True)

    store = GitTagStore(ROOT)
    result = anchor_release(ROOT, git_store=store)
    print(anchor_summary(result))

    if args.push:
        subprocess.run(
            ["git", "-C", str(ROOT), "push", "origin", result.tag_name],
            check=True,
        )
        print(f"已推送锚点 tag：{result.tag_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
