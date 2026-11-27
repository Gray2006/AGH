"""从真实仓库里筛出可判别的仓库级任务。

用法：
    python scripts/bench_scan.py --repo runs/agi-bench/click --limit 12

一道可用任务 = 父提交代码 + 修复提交的测试 → 失败；再应用修复的源码 → 通过。
只跑该提交改动的测试文件，比跑全量快一个量级。

输出 JSON 到 --out（默认 <repo>/../tasks-<repo名>.json）。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

FIX_WORDS = re.compile(
    r"\b(fix|bug|crash|wrong|incorrect|error|regression|broken|fail|issue|"
    r"handle|avoid|prevent|respect|support|allow|ensure|correct)\b",
    re.I,
)


def git(repo: pathlib.Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)
    return proc.stdout.strip()


def env_for(repo: pathlib.Path) -> dict[str, str]:
    env = dict(os.environ)
    src = repo / "src"
    if src.exists():
        prefix = str(src)
        env["PYTHONPATH"] = prefix + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def run_tests(repo: pathlib.Path, test_files: list[str], timeout: int) -> tuple[bool, str]:
    if not test_files:
        return True, "no tests"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header",
             "-p", "no:cacheprovider", *test_files],
            cwd=repo, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env_for(repo),
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    lines = (proc.stdout or "").strip().splitlines()
    return proc.returncode == 0, lines[-1] if lines else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--scan", type=int, default=400, help="扫描多少个提交")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    branch = next((b for b in ("main", "master", "stable") if b in git(repo, "branch")), "main")
    git(repo, "reset", "--hard", "--quiet", branch)
    git(repo, "clean", "-fdq")

    shas = git(repo, "log", "--format=%H", "-n", str(args.scan)).splitlines()
    print(f"扫描 {len(shas)} 个提交：{repo.name}")

    usable: list[dict] = []
    scanned = 0
    for sha in shas:
        files = [f for f in git(repo, "show", "--name-only", "--format=", sha).splitlines() if f]
        src = [f for f in files if f.startswith("src/") and f.endswith(".py")]
        tst = [f for f in files if f.startswith("tests/") and f.endswith(".py")]
        if not (src and tst):
            continue
        subject = git(repo, "log", "-1", "--format=%s", sha)
        if not FIX_WORDS.search(subject):
            continue
        if subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{sha}^"],
                          cwd=repo, capture_output=True).returncode != 0:
            continue

        scanned += 1
        try:
            git(repo, "reset", "--hard", "--quiet", f"{sha}^")
            git(repo, "clean", "-fdq")
            git(repo, "checkout", sha, "--", *tst)
            base_ok, base_tail = run_tests(repo, tst, args.timeout)
            if base_ok:
                continue
            git(repo, "checkout", sha, "--", *src)
            fixed_ok, _ = run_tests(repo, tst, args.timeout)
        except subprocess.CalledProcessError:
            continue

        if fixed_ok:
            usable.append({
                "sha": sha, "subject": subject, "src_files": src,
                "test_files": tst, "base_tail": base_tail[:200],
            })
            print(f"[{len(usable):>2}] {sha[:8]} {subject[:60]}")
        if len(usable) >= args.limit:
            break

    git(repo, "reset", "--hard", "--quiet", branch)
    git(repo, "clean", "-fdq")

    print(f"\n扫描 {scanned} 个候选，可用 {len(usable)} 个")
    out = pathlib.Path(args.out) if args.out else repo.parent / f"tasks-{repo.name}.json"
    out.write_text(json.dumps(usable, ensure_ascii=False, indent=2), encoding="utf-8")
    print("写到:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
