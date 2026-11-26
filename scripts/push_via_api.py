"""在 github.com:443 不可达、但 api.github.com 可达时，用 Git Data API 推送本地提交。

用法：
    $env:GH_TOKEN = gh auth token
    python scripts/push_via_api.py [branch]

做的事：把 `origin/<branch>` 之后的每个本地提交按原 tree / 作者 / 时间 / message 重建，
校验回传 sha 与本地一致后更新 ref；随后把指向这些提交的本地 tag 也建到远程。
sha 一致是关键：远程与本地不会分叉。
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = os.environ.get("GH_TOKEN") or ""
SIG_RE = re.compile(r"^(?P<name>.*) <(?P<email>[^>]*)> (?P<ts>\d+) (?P<tz>[+-]\d{4})$")


def git(*args: str) -> str:
    return git_raw(*args).strip()


def git_raw(*args: str) -> str:
    # 显式用 UTF-8：Windows 默认按 GBK 解码，中文 commit/tag message 会炸
    # （UnicodeDecodeError 发生在读取线程里，stdout 变成 None）
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def iso(ts: int, tz: str) -> str:
    sign = 1 if tz[0] == "+" else -1
    offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
    return datetime.fromtimestamp(ts, tz=timezone(offset)).isoformat(timespec="seconds")


def parse_identity(line: str) -> dict[str, str]:
    m = SIG_RE.match(line)
    if not m:
        raise SystemExit(f"无法解析身份行: {line}")
    return {
        "name": m["name"],
        "email": m["email"],
        "date": iso(int(m["ts"]), m["tz"]),
    }


def read_commit(sha: str) -> dict:
    raw = git_raw("cat-file", "-p", sha)
    headers, _, message = raw.partition("\n\n")
    fields: dict[str, str] = {}
    for line in headers.splitlines():
        key, _, value = line.partition(" ")
        fields.setdefault(key, value)
    return {
        "tree": fields["tree"],
        "parents": [
            ln.split(" ", 1)[1] for ln in headers.splitlines() if ln.startswith("parent ")
        ],
        "author": parse_identity(fields["author"]),
        "committer": parse_identity(fields["committer"]),
        "message": message,
    }


def call(method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    if not TOKEN:
        raise SystemExit("缺少 GH_TOKEN（先跑 gh auth token）")
    remote = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[/:](?P<owner>[^/]+)/(?P<repo>[^/.]+)", remote)
    if not m:
        raise SystemExit(f"无法从 remote 解析仓库: {remote}")
    owner, repo = m["owner"], m["repo"]
    api = f"https://api.github.com/repos/{owner}/{repo}"
    branch = sys.argv[1] if len(sys.argv) > 1 else "main"

    ref = call("GET", f"{api}/git/ref/heads/{branch}")
    remote_head = ref["object"]["sha"]
    pending = git("rev-list", "--reverse", f"{remote_head}..HEAD").split()
    if not pending:
        print("没有待推送的提交")
    for sha in pending:
        info = read_commit(sha)
        assert info["parents"] == [remote_head], "只支持线性历史"
        parent_tree = call("GET", f"{api}/git/commits/{remote_head}")["tree"]["sha"]
        entries = []
        for line in git("diff", "--name-status", remote_head, sha).splitlines():
            status, path = line.split("\t", 1)
            if status.startswith("D"):
                entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue
            content = subprocess.run(
                ["git", "show", f"{sha}:{path}"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            blob = call(
                "POST",
                f"{api}/git/blobs",
                {"content": base64.b64encode(content).decode(), "encoding": "base64"},
            )["sha"]
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob})
        tree = call(
            "POST", f"{api}/git/trees", {"base_tree": parent_tree, "tree": entries}
        )["sha"]
        if tree != info["tree"]:
            raise SystemExit(f"{sha[:7]}: tree 不一致，停止（删除的文件未支持）")
        commit = call(
            "POST",
            f"{api}/git/commits",
            {
                "message": info["message"],
                "tree": tree,
                "parents": [remote_head],
                "author": info["author"],
                "committer": info["committer"],
            },
        )["sha"]
        if commit != sha:
            raise SystemExit(f"{sha[:7]}: 重建出的 commit 为 {commit[:7]}，停止")
        call("PATCH", f"{api}/git/refs/heads/{branch}", {"sha": commit, "force": False})
        remote_head = commit
        print(f"pushed {sha[:7]} {info['message'].splitlines()[0]}")

    for tag in git("tag", "--points-at", remote_head).split():
        try:
            call("GET", f"{api}/git/ref/tags/{tag}")
            print(f"tag {tag} 已存在，跳过")
            continue
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        raw = git_raw("cat-file", "-p", f"refs/tags/{tag}")
        headers, _, message = raw.partition("\n\n")
        tagger_line = next(
            ln for ln in headers.splitlines() if ln.startswith("tagger ")
        )
        tag_obj = call(
            "POST",
            f"{api}/git/tags",
            {
                "tag": tag,
                "message": message,
                "object": remote_head,
                "type": "commit",
                "tagger": parse_identity(tagger_line[len("tagger ") :]),
            },
        )
        call(
            "POST",
            f"{api}/git/refs",
            {"ref": f"refs/tags/{tag}", "sha": tag_obj["sha"]},
        )
        print(f"tag {tag} -> {tag_obj['sha'][:7]}")


if __name__ == "__main__":
    main()
