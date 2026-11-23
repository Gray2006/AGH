"""版本号一致性：pyproject、包内 __version__、CHANGELOG 必须同步。

改版本时三处一起改，否则这里会红。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import agh

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_version_matches_package() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == agh.__version__


def test_changelog_has_section_for_current_version() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{agh.__version__}]" in text
