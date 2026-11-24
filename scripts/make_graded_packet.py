"""生成分级标注包：每题回答 0 / 0.5 / 1。

用于概率校准：验证器给的是连续分，人工给分级标签，才能算 ECE。

    python scripts/make_graded_packet.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.contracts import GestaltReconstruction, Skeleton  # noqa: E402
from agh.verifier import StructuralVerifier  # noqa: E402

BAR = "=" * 60


def main() -> int:
    parser = argparse.ArgumentParser(description="分级标注包")
    parser.add_argument(
        "--candidates",
        type=Path,
        nargs="+",
        default=[ROOT / "runs" / "g1" / "llm-hard50-candidates.json"],
    )
    parser.add_argument("--out-md", type=Path, default=ROOT / "runs" / "g1" / "label-graded.md")
    parser.add_argument("--out-json", type=Path, default=ROOT / "runs" / "g1" / "label-graded-template.json")
    parser.add_argument("--out-candidates", type=Path, default=ROOT / "runs" / "g1" / "label-graded-candidates.json")
    parser.add_argument("--per-bucket", type=int, default=3)
    args = parser.parse_args()

    items = []
    for path in args.candidates:
        items.extend(json.loads(path.read_text(encoding="utf-8")))
    verifier = StructuralVerifier()
    buckets: dict[float, list[dict]] = {}
    for item in items:
        skeleton = Skeleton.model_validate(item["skeleton"])
        if not any(m.vertical for m in skeleton.moves):
            continue
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        score = round(verifier.score(recon, skeleton), 3)
        buckets.setdefault(score, []).append(item)

    picked: list[dict] = []
    for score in sorted(buckets, reverse=True):
        picked.extend(buckets[score][: args.per_bucket])

    lines = [
        "# AGH 分级标注",
        "",
        "每题给一个 0 / 0.5 / 1：",
        "- 1  = 所有垂直节点都在 parts 里，且都有边指向它们",
        "- 0.5 = 部分被支持（有的缺节点，有的缺边）",
        "- 0  = 基本没有支持",
        "",
        BAR,
        "",
    ]
    template = []
    for index, item in enumerate(picked):
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        vnodes = [m.node for m in skeleton.moves if m.vertical]
        edges = recon.content.get("edges", [])
        lines += [
            BAR,
            f"  第 {index + 1} 题",
            BAR,
            "",
            f"骨架节点：{', '.join(skeleton.nodes)}",
            f"骨架边：{'; '.join(f'{a}->{b}' for a, b in skeleton.edges)}",
            f"垂直节点：{', '.join(vnodes)}",
            "",
            f"候选 parts：{', '.join(recon.parts)}",
            f"候选 edges：{'; '.join(f'{a}->{b}' for a, b in edges) or '（空）'}",
            "",
            "答案（0 / 0.5 / 1）：____",
            "",
        ]
        template.append({"index": index, "label": None})

    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    args.out_json.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_candidates.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"题目: {args.out_md}")
    print(f"共 {len(picked)} 题，覆盖分数 {sorted(buckets, reverse=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
