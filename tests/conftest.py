from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.pipeline import make_demo_frozen  # noqa: E402

FROZEN_SRC = ROOT / "config" / "frozen"


@pytest.fixture()
def frozen_root(tmp_path: Path) -> Path:
    return make_demo_frozen(tmp_path)


@pytest.fixture()
def frozen_src() -> Path:
    return FROZEN_SRC
