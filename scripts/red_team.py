"""红队演练入口：python scripts/red_team.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.redteam import report, run_attacks  # noqa: E402


def main() -> int:
    results = run_attacks(ROOT / "config" / "frozen")
    payload = report(results)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["all_defended"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
