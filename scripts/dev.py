"""开发者常用命令的跨平台入口。

为什么不用 Makefile：这个项目主要在 Windows 上开发，`make` 不一定有。
Python 脚本在所有平台上行为一致。

用法：
    python scripts/dev.py test
    python scripts/dev.py lint
    python scripts/dev.py check     # lint + test
    python scripts/dev.py build
    python scripts/dev.py docs
    python scripts/dev.py clean
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, env_extra: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    import os

    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.call(cmd, cwd=ROOT, env=env)


def cmd_test() -> int:
    return run(
        [sys.executable, "-m", "pytest", "-q", "--cov=agh", "--cov-report=term", "--cov-fail-under=88"]
    )


def cmd_lint() -> int:
    code = run([sys.executable, "-m", "ruff", "check", "agh", "tests", "scripts", "examples"])
    if code != 0:
        return code
    code = run([sys.executable, "-m", "mypy", "agh"])
    if code != 0:
        return code
    return run([sys.executable, "-m", "vulture", "agh", "--min-confidence", "80"])


def cmd_check() -> int:
    code = cmd_lint()
    if code != 0:
        return code
    return cmd_test()


def cmd_build() -> int:
    code = run([sys.executable, "-m", "build"])
    if code != 0:
        return code
    return run([sys.executable, "-m", "twine", "check", "dist/*"])


def cmd_docs() -> int:
    return run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        env_extra={"NO_MKDOCS_2_WARNING": "1"},
    )


def cmd_clean() -> int:
    for name in ("dist", "build", "site", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage"):
        target = ROOT / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            print("removed", name)
        elif target.is_file():
            target.unlink(missing_ok=True)
            print("removed", name)
    return 0


COMMANDS = {
    "test": cmd_test,
    "lint": cmd_lint,
    "check": cmd_check,
    "build": cmd_build,
    "docs": cmd_docs,
    "clean": cmd_clean,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(__doc__)
        print("可用命令：", ", ".join(COMMANDS))
        return 2
    return COMMANDS[argv[0]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
