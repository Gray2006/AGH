"""兼容旧用法：`python scripts/run_m0.py`。等价于 `python -m agh`。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
