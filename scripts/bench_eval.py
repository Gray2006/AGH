"""评估候选补丁：父提交代码 + 修复后的测试 + 候选改动 → 跑测试。

用法：
    python scripts/bench_eval.py --repo runs/agi-bench/click \
        --manifest runs/agi-bench/manifest.json --out runs/agi-bench/baseline.json

manifest 每项需要：id / sha / test_files / workdir。
workdir 是候选改过的工作副本，脚本用 `git diff` 取它的改动。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys


def git(cwd: pathlib.Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)
    return proc.stdout.strip()


def force_rmtree(path: pathlib.Path) -> None:
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=_onerror)


def candidate_patch(workdir: pathlib.Path) -> str:
    """取候选的全部改动（含新增文件）。

    不能 strip：补丁末尾的换行是格式的一部分，去掉会变成 corrupt patch。
    """
    git(workdir, "add", "-A")
    return subprocess.run(
        ["git", "diff", "--cached", "HEAD"], cwd=workdir,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def evaluate(repo: pathlib.Path, item: dict, eval_root: pathlib.Path, timeout: int) -> dict:
    sha = item["sha"]
    tests = item["test_files"]
    workdir = pathlib.Path(item["workdir"])

    patch = candidate_patch(workdir)
    if not patch.strip():
        return {**item, "passed": None, "reason": "候选还没产出改动", "patch_lines": 0}

    dest = eval_root / item["id"]
    force_rmtree(dest)

    git(repo, "reset", "--hard", "--quiet", f"{sha}^")
    git(repo, "clean", "-fdq")
    git(repo, "checkout", sha, "--", *tests)
    shutil.copytree(repo, dest, symlinks=True)
    git(repo, "reset", "--hard", "--quiet", "HEAD")

    apply = subprocess.run(
        ["git", "apply", "-p1", "--whitespace=nowarn", "-"],
        cwd=dest, input=patch, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if apply.returncode != 0:
        return {
            **item, "passed": False,
            "reason": f"补丁无法应用：{(apply.stderr or apply.stdout).strip()[:200]}",
            "patch_lines": len(patch.splitlines()),
        }

    env = dict(os.environ)
    env["PYTHONPATH"] = str(dest / "src")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", *tests],
            cwd=dest, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return {**item, "passed": False, "reason": "测试超时",
                "patch_lines": len(patch.splitlines())}

    tail = (proc.stdout or "").strip().splitlines()
    return {
        **item,
        "passed": proc.returncode == 0,
        "reason": "" if proc.returncode == 0 else "测试未全绿",
        "tail": tail[-1] if tail else "",
        "patch_lines": len(patch.splitlines()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    eval_root = repo.parent / "eval"
    eval_root.mkdir(exist_ok=True)
    branch = next((b for b in ("main", "master", "stable") if b in git(repo, "branch")), "main")

    results = []
    for item in manifest:
        r = evaluate(repo, item, eval_root, args.timeout)
        results.append(r)
        mark = "PASS" if r["passed"] else ("FAIL" if r["passed"] is False else "PEND")
        print(f"{item['id']} {mark:<4} {item.get('subject', '')[:52]}")
        if r["passed"] is False:
            print(f"      {r['reason']} {r.get('tail', '')[:80]}")

    git(repo, "reset", "--hard", "--quiet", branch)
    git(repo, "clean", "-fdq")

    done = [r for r in results if r["passed"] is not None]
    passed = sum(1 for r in done if r["passed"])
    print(f"\n已完成 {len(done)}/{len(results)}，通过 {passed}/{len(done)}"
          + (f" = {passed / len(done) * 100:.0f}%" if done else ""))

    out = pathlib.Path(args.out) if args.out else repo.parent / "baseline.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("写到:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
