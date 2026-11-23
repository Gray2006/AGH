"""用真模型跑一次子级重构（单次，不进化）。

    set DEEPSEEK_API_KEY=...        # Windows
    python scripts/run_llm_child.py --provider deepseek

换别的 OpenAI 兼容端点用 --base-url / --model / --api-key-env。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.arena import ArenaConfig  # noqa: E402
from agh.llm import ChildOutputError, LlmChild  # noqa: E402
from agh.pipeline import PARENT_SIG, m0_skeleton  # noqa: E402
from agh.providers import make_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="用真模型跑一次 AGH 子级重构")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    args = parser.parse_args()

    client = make_client(
        args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
    )
    client.max_tokens = args.max_tokens
    child = LlmChild(
        name="llm-child",
        complete=client,
        skeleton=m0_skeleton(),
        parent_features=PARENT_SIG.features,
    )
    try:
        recon = child.reconstruct("ct-llm-demo")
    except ChildOutputError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "errors": exc.errors}, ensure_ascii=False, indent=2))
        return 1

    cfg = ArenaConfig.from_frozen(ROOT / "config" / "frozen")
    from agh.arena import score_candidate

    breakdown = score_candidate(
        recon, m0_skeleton(), cfg, verifier_score=None, parent_signature=PARENT_SIG
    )
    print(
        json.dumps(
            {
                "ok": True,
                "model": client.model,
                "child": recon.child_id,
                "parts": list(recon.parts),
                "features": list(recon.signature.features),
                "self_confidence": recon.self_confidence,
                "score": round(breakdown.score, 5),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
