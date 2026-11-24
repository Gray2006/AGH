"""生成人工标注包：把候选重构渲染成是非题，人只需填 0/1。

    python scripts/make_label_packet.py

产出：
- runs/g1/label-packet.md   人看的是非题
- runs/g1/label-template.json  机器读的答案模板（把 null 改成 0 或 1）
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


def main() -> int:
    parser = argparse.ArgumentParser(description="生成人工标注包")
    parser.add_argument("--candidates", type=Path, default=ROOT / "runs" / "g1" / "llm-bench-candidates.json")
    parser.add_argument("--out-md", type=Path, default=ROOT / "runs" / "g1" / "label-packet.md")
    parser.add_argument("--out-json", type=Path, default=ROOT / "runs" / "g1" / "label-template.json")
    args = parser.parse_args()

    items = json.loads(args.candidates.read_text(encoding="utf-8"))
    lines = [
        "# AGH 标注包",
        "",
        "每题回答一个问题：**这个候选用结构证据支持了骨架要求的垂直移动吗？**",
        "",
        "判断标准（只有两条）：",
        "1. 该垂直移动的节点，出现在候选的 `parts` 里；",
        "2. 候选的 `edges` 里有一条边指向它。",
        "",
        "两条都满足记 1，否则记 0。不需要看别的，也不用管分数。",
        "",
        "---",
        "",
    ]
    template = []
    for index, item in enumerate(items):
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        vertical = [m.node for m in skeleton.moves if m.vertical]
        lines += [
            f"## 第 {index} 题",
            "",
            f"- 骨架节点：{', '.join(skeleton.nodes)}",
            f"- 骨架边：{'; '.join(f'{a}->{b}' for a, b in skeleton.edges)}",
            f"- 要求的垂直移动节点：{', '.join(vertical) if vertical else '（无）'}",
            f"- 候选 parts：{', '.join(recon.parts)}",
            f"- 候选 edges：{'; '.join(f'{a}->{b}' for a, b in recon.content.get('edges', [])) or '（空）'}",
            "",
            "答案：____（填 0 或 1）",
            "",
        ]
        template.append({"index": index, "skeleton": skeleton.skeleton_id, "label": None})
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    args.out_json.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"题目: {args.out_md}")
    print(f"答案模板: {args.out_json}")
    print(f"共 {len(items)} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
