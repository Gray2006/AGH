"""从真实模型样本里挑 5 个失败 + 5 个正例，生成语义校准包。

    python scripts/make_real_packet.py --candidates runs/g1/llm-hard50-candidates.json

失败样本 = 结构验证器 < 1.0 的真实输出（不是构造出来的负例）。
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
    parser = argparse.ArgumentParser(description="真实失败样本校准包")
    parser.add_argument("--candidates", type=Path, default=ROOT / "runs" / "g1" / "llm-hard50-candidates.json")
    parser.add_argument("--out-md", type=Path, default=ROOT / "runs" / "g1" / "label-real.md")
    parser.add_argument("--out-json", type=Path, default=ROOT / "runs" / "g1" / "label-real-template.json")
    parser.add_argument("--out-candidates", type=Path, default=ROOT / "runs" / "g1" / "label-real-candidates.json")
    parser.add_argument("--failures", type=int, default=5)
    parser.add_argument("--positives", type=int, default=5)
    args = parser.parse_args()

    items = json.loads(args.candidates.read_text(encoding="utf-8"))
    verifier = StructuralVerifier()
    failures: list[dict] = []
    positives: list[dict] = []
    for item in items:
        skeleton = Skeleton.model_validate(item["skeleton"])
        recon = GestaltReconstruction.model_validate(item["reconstruction"])
        if not any(m.vertical for m in skeleton.moves):
            continue  # 没有垂直移动，「是否支持」无定义
        score = verifier.score(recon, skeleton)
        if score < 1.0:
            failures.append({**item, "_verifier": score})
        elif score == 1.0:
            positives.append({**item, "_verifier": score})

    picked = failures[: args.failures] + positives[: args.positives]
    if not failures:
        print("没有真实失败样本")
        return 1

    lines = [
        "# AGH 真实样本标注",
        "",
        "规则：垂直节点在候选 parts 里、且候选 edges 里有边指向它，才算支持。",
        "全部垂直节点都被支持填 1，否则填 0。",
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
            f"要求的垂直移动节点：{', '.join(vnodes)}",
            "",
            f"候选 parts：{', '.join(recon.parts)}",
            f"候选 edges：{'; '.join(f'{a}->{b}' for a, b in edges) or '（空）'}",
            "",
            "答案（0 或 1）：____",
            "",
        ]
        template.append({"index": index, "label": None})

    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    args.out_json.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_candidates.write_text(
        json.dumps(
            [{k: v for k, v in item.items() if not k.startswith("_")} for item in picked],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"题目: {args.out_md}")
    n_fail = min(len(failures), args.failures)
    n_pos = min(len(positives), args.positives)
    print(f"失败样本 {n_fail} 个，正例 {n_pos} 个，共 {len(picked)} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
