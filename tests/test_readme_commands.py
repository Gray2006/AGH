"""README 里出现的每个 `agh <command>` 都必须真实存在。

文档和实现漂移是最常见的「看起来能用其实不能」。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMAND_RE = re.compile(r"\bagh ([a-z][a-z0-9-]*)")


def _readme_commands() -> set[str]:
    found: set[str] = set()
    for name in ("README.md", "README.en.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        # 只看代码块里的命令，避免正文里提到命令名时误判
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.DOTALL):
            for match in COMMAND_RE.finditer(block):
                found.add(match.group(1))
    return found


def _known_commands() -> set[str]:
    from agh.cli import build_parser

    parser = build_parser()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            return set(action.choices)
    return set()


def test_readme_commands_exist() -> None:
    readme = _readme_commands()
    known = _known_commands()
    assert readme, "README 里没找到任何 agh 命令，正则可能失效了"
    unknown = sorted(readme - known)
    assert not unknown, f"README 提到但实现里没有的命令：{unknown}"


def test_known_commands_have_help() -> None:
    """每个子命令都要能 --help，不能有注册了但崩掉的命令。"""
    from agh.cli import main

    for cmd in sorted(_known_commands()):
        with pytest.raises(SystemExit) as exc:
            main([cmd, "--help"])
        assert exc.value.code == 0, f"agh {cmd} --help 退出码不是 0"
