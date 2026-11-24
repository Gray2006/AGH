"""发布流程：版本校验 → 跑一次 M0 → 把事件日志锚定到 git tag。

锚定的意义：本地 events.jsonl 可以被删掉重写成一条自洽的新链，
但如果链头已经作为 tag 推到远程仓库，替换就必须同时改远程——那是另一个权限面。
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .anchoring import Anchor, AnchorStore, GitTagStore, anchor_log, check_log
from .crypto import Key
from .eventlog import EventLog
from .pipeline import DEV_KID, dev_keyring, run_m0


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class ReleaseResult:
    version: str
    run_dir: Path
    anchor: Anchor
    local_store: Path
    tag_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "run_dir": str(self.run_dir),
            "head": self.anchor.head,
            "size": self.anchor.size,
            "anchor_tag": self.tag_name,
            "local_store": str(self.local_store),
        }


def read_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    package = (root / "agh" / "__init__.py").read_text(encoding="utf-8")
    marker = '__version__ = "'
    start = package.index(marker) + len(marker)
    declared = package[start : package.index('"', start)]
    if version != declared:
        raise ReleaseError(f"版本不一致：pyproject={version} 包内={declared}")
    return version


def require_clean_tree(repo: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    if proc.stdout.strip():
        raise ReleaseError("工作区不干净，先提交再发布")


def git_tag_exists(repo: Path, name: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "tag", "-l", name],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(proc.stdout.strip())


def anchor_release(
    root: Path,
    *,
    run_dir: Path | None = None,
    key: Key | None = None,
    git_store: GitTagStore | None = None,
    create_tag: bool = True,
    store_path: Path | None = None,
) -> ReleaseResult:
    """跑一次 M0，把事件日志的链头锚定到本地 JSONL 与 git tag。"""
    root = Path(root)
    version = read_version(root)
    run_dir = Path(run_dir) if run_dir is not None else root / "runs" / "release" / f"v{version}"
    if run_dir.exists():
        import shutil

        shutil.rmtree(run_dir)
    report = run_m0(
        frozen_root=root / "config" / "frozen",
        run_dir=run_dir,
        include_dissent=True,
        human_approved=True,
    )
    if not report.l1_bit_exact:
        raise ReleaseError("M0 的 L1 重放不是逐位一致，拒绝锚定")

    log = EventLog(run_dir / "events.jsonl")
    signing_key = key if key is not None else dev_keyring("ed25519").get(DEV_KID)
    # 锚点里只存 posix 相对路径：Windows 绝对路径的反斜杠进 JSON 会被命令行/编辑器
    # 层层转义，存进 git tag 后可能变成非法 JSON。
    try:
        rel = run_dir.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = run_dir.name
    anchor = anchor_log(
        log, key=signing_key, label=f"m0-v{version}", log_path=f"{rel}/events.jsonl"
    )

    local = AnchorStore(store_path or root / "runs" / "anchors" / f"v{version}.jsonl")
    local.append(anchor)

    tag_name = ""
    if create_tag and git_store is not None:
        tag_name = git_store.append(anchor)
    return ReleaseResult(
        version=version,
        run_dir=run_dir,
        anchor=anchor,
        local_store=local.path,
        tag_name=tag_name,
    )


def verify_release(
    root: Path,
    *,
    version: str | None = None,
    git_store: GitTagStore | None = None,
    store_path: Path | None = None,
) -> dict[str, Any]:
    """按版本找最新锚点，校验事件日志是否仍是锚定时的样子。"""
    root = Path(root)
    version = version or read_version(root)
    store = AnchorStore(store_path or root / "runs" / "anchors" / f"v{version}.jsonl")
    anchors = store.read()
    if not anchors:
        raise ReleaseError(f"没有 v{version} 的锚点：{store.path}")
    log = EventLog(root / "runs" / "release" / f"v{version}" / "events.jsonl")
    # 只认指向这份日志的锚点：别的运行（测试、临时目录）写的锚点不能拿来比
    expected = log.path
    matching = [a for a in anchors if (root / a.log_path).resolve() == expected.resolve()]
    if not matching:
        raise ReleaseError(f"没有指向 {expected} 的锚点")
    anchor = matching[-1]
    keyring = dev_keyring("ed25519")
    signed = check_log(log, anchor, keyring=keyring)
    return {
        "version": version,
        "head": anchor.head,
        "size": anchor.size,
        "signature_verified": signed,
        "tag": git_store.read() if git_store is not None else None,
    }


def anchor_summary(result: ReleaseResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2)


__all__ = [
    "ReleaseError",
    "ReleaseResult",
    "anchor_release",
    "anchor_summary",
    "git_tag_exists",
    "read_version",
    "require_clean_tree",
    "verify_release",
]
