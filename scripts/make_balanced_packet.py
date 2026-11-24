"""生成平衡标注包：5 个正例 + 5 个负例，题间用粗分隔线。

    python scripts/make_balanced_packet.py

负例由「删掉一条指向垂直节点的边」或「把垂直节点从 parts 里删掉」构造，
构造后先用结构验证器确认得分为 0，再写进包。
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agh.contracts import GestaltReconstruction, Skeleton  # noqa: E402
from agh.verifier import StructuralVerifier  # noqa: E402

BAR = "=" * 60


def vertical_nodes(skeleton: Skeleton) -> list[str]:
    return [m.node for m in skeleton.moves if m.vertical]


def make_negative(recon: dict, skeleton: Skeleton) -> dict | None:
    """删掉所有指向垂直节点的边与特征；还支持就再删节点。"""
    targets = set(vertical_nodes(skeleton))
    if not targets:
        return None
    candidate = deepcopy(recon)
    edges = candidate["content"].get("edges", [])
    candidate["content"]["edges"] = [
        e for e in edges if not (isinstance(e, list) and len(e) == 2 and e[1] in targets)
    ]
    features = candidate.get("signature", {}).get("features", [])
    candidate["signature"]["features"] = [
        f for f in features if not (isinstance(f, str) and "-" in f and f.split("-", 1)[1] in targets)
    ]
    candidate["parts"] = [p for p in candidate["parts"] if p not in targets]
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="生成平衡标注包")
    parser.add_argument("--candidates", type=Path, default=ROOT / "runs" / "g1" / "llm-bench-candidates.json")
    parser.add_argument("--out-md", type=Path, default=ROOT / "runs" / "g1" / "label-balanced.md")
    parser.add_argument("--out-json", type=Path, default=ROOT / "runs" / "g1" / "label-balanced-template.json")
    parser.add_argument("--out-candidates", type=Path, default=ROOT / "runs" / "g1" / "label-balanced-candidates.json")
    parser.add_argument("--positives", type=int, default=5)
    parser.add_argument("--negatives", type=int, default=5)
    args = parser.parse_args()

    items = json.loads(args.candidates.read_text(encoding="utf-8"))
    verifier = StructuralVerifier()
    usable = []
    for item in items:
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        if vertical_nodes(skeleton) and verifier.score(recon, skeleton) == 1.0:
            usable.append(item)

    packed: list[dict] = []
    for item in usable[: args.positives]:
        packed.append({"item": item, "label": 1})
    for item in usable[: args.negatives]:
        skeleton = Skeleton.model_validate(item["skeleton"])
        negative = make_negative(item["reconstruction"], skeleton)
        if negative is None:
            continue
        recon = GestaltReconstruction.model_validate(negative)
        if verifier.score(recon, skeleton) != 0.0:
            continue
        packed.append({"item": {"skeleton": item["skeleton"], "reconstruction": negative}, "label": 0})

    lines = [
        "# AGH 平衡标注包",
        "",
        "每题只回答一个问题：**这个候选用结构证据支持了骨架要求的垂直移动吗？**",
        "",
        "判断只有两条：",
        "1. 该垂直移动的节点，出现在候选的 parts 里；",
        "2. 候选的 edges 里有一条边指向它。",
        "",
        "两条都满足填 1，否则填 0。全部满足才填 1。",
        "",
        BAR,
        "",
    ]
    template = []
    for index, row in enumerate(packed):
        skeleton = Skeleton.model_validate(row["item"]["skeleton"])
        recon = GestaltReconstruction.model_validate(row["item"]["reconstruction"])
        vnodes = vertical_nodes(skeleton)
        edges = recon.content.get("edges", [])
        lines += [
            BAR,
            f"  第 {index + 1} 题",
            BAR,
            "",
            f"骨架节点：{', '.join(skeleton.nodes)}",
            f"骨架边：{'; '.join(f'{a}->{b}' for a, b in skeleton.edges)}",
            f"要求的垂直移动节点：{', '.join(vnodes)}",
            "",
            f"候选 parts：{', '.join(recon.parts)}",
            f"候选 edges：{'; '.join(f'{a}->{b}' for a, b in edges) or '（空）'}",
            "",
            "答案（0 或 1）：____",
            "",
            BAR,
            "",
        ]
        template.append({"index": index, "label": None})
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    args.out_json.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_candidates.write_text(
        json.dumps([row["item"] for row in packed], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"题目: {args.out_md}")
    print(f"答案模板: {args.out_json}")
    print(f"候选: {args.out_candidates}")
    pos = sum(1 for r in packed if r["label"] == 1)
    neg = sum(1 for r in packed if r["label"] == 0)
    print(f"共 {len(packed)} 题（正例 {pos}，负例 {neg}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
