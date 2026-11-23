"""命令行入口：`python -m agh` 或 `agh`。

子命令：
    run         跑 M0 垂直切片（默认）
    verify      校验事件日志哈希链
    replay      L1 逐位重放
    experiment  G1 竞技场实验
    ablation    9 组消融
    version     版本号
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import __version__
from .crypto import KeyRing
from .eventlog import EventLog
from .evolution import EvolutionConfig, Strategy, default_benchmarks, evolve
from .evolution_llm import compare_search
from .frozen import FrozenLayer
from .pipeline import DEV_KID, DEV_SECRET, PARENT_SIG, faithful_child, m0_skeleton, run_m0
from .sdk import AghClient, default_frozen_root


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _prepare(root: Path, refresh_anchor: bool) -> Path:
    frozen = root / "config" / "frozen"
    if not frozen.is_dir():
        raise SystemExit(f"找不到冻结配置目录: {frozen}")
    anchor = root / "config" / "anchor.json"
    keyring = KeyRing.with_secret(DEV_KID, DEV_SECRET)
    layer = FrozenLayer(frozen)
    if anchor.exists() and not refresh_anchor:
        layer.verify(anchor, keyring)
        print(f"锚点校验通过: {anchor}")
    else:
        layer.write_anchor(anchor, keyring, DEV_KID)
        print(f"锚点已{'重建' if anchor.exists() else '生成'}: {anchor}")
    return frozen


def cmd_run(args: argparse.Namespace) -> int:
    root = (args.root or repo_root()).resolve()
    frozen = _prepare(root, args.refresh_anchor)
    run_dir = (args.out or root / "runs" / "m0").resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report = run_m0(
        frozen_root=frozen,
        run_dir=run_dir,
        include_dissent=not args.no_dissent,
        human_approved=not args.no_approve,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n事件日志: {run_dir / 'events.jsonl'}")
    print(f"报告: {run_dir / 'report.json'}")
    return 0 if report.l1_bit_exact else 1


def cmd_verify(args: argparse.Namespace) -> int:
    client = AghClient(run_dir=args.run_dir)
    ok = client.verify_log()
    print(json.dumps({"ok": ok, "log": str(client.run_dir / "events.jsonl")}, ensure_ascii=False))
    return 0 if ok else 1


def cmd_replay(args: argparse.Namespace) -> int:
    client = AghClient(run_dir=args.run_dir)
    report = client.replay()
    payload = {
        "steps": report.steps,
        "mismatches": report.mismatches,
        "bit_exact": report.bit_exact,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.bit_exact else 1


def cmd_experiment(args: argparse.Namespace) -> int:
    client = AghClient(frozen_root=args.frozen or default_frozen_root())
    report = client.experiment(seeds=args.seeds, resamples=args.resamples)
    target = report.write(args.out)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n报告: {target}")
    return 0


def cmd_ablation(args: argparse.Namespace) -> int:
    client = AghClient(frozen_root=args.frozen or default_frozen_root())
    report = client.ablation(seeds=args.seeds, resamples=args.resamples)
    target = report.write(args.out)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n报告: {target}")
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    from .arena import ArenaConfig

    root = (args.root or repo_root()).resolve()
    frozen = _prepare(root, args.refresh_anchor)
    cfg = ArenaConfig.from_frozen(frozen)
    if args.benchmarks > 0:
        from .benchmarks import feature_pool as bench_features
        from .benchmarks import generate_benchmarks

        benches = generate_benchmarks(args.benchmarks, seed=args.bench_seed)
        nodes = benches[0].skeleton.nodes
        complete = [f"{nodes[i]}-{nodes[j]}" for i in range(len(nodes)) for j in range(i + 1, len(nodes))]
        seed = Strategy(
            name="seed-gen",
            features=tuple(complete),
            parts=tuple(nodes),
            covered=tuple(nodes),
            confidence=0.6,
            depth=0.7,
        )
        _ = bench_features  # 保留给特征池用
    else:
        benches = default_benchmarks(m0_skeleton(), PARENT_SIG.features)
        seed_recon = faithful_child("ct-seed")
        seed = Strategy(
            name="seed-faithful",
            features=tuple(seed_recon.signature.features),
            parts=tuple(seed_recon.parts),
            covered=tuple(seed_recon.coverage.covered),
            confidence=seed_recon.self_confidence,
            depth=0.9,
        )
    active_mutator = None
    if args.llm_mutator:
        from .benchmarks import feature_pool as bench_features
        from .evolution_llm import LlmStrategyMutator
        from .providers import make_client

        feature_pool = bench_features(benches) or sorted(
            {f for b in benches for f in b.parent.features}
        )
        node_pool = sorted({n for b in benches for n in b.skeleton.nodes})
        client = make_client(
            args.provider, model=args.model, api_key_env=args.api_key_env
        )
        active_mutator = LlmStrategyMutator(feature_pool, node_pool, complete=client)
    log_path = args.out.parent / "events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()
    report = evolve(
        seed,
        benches,
        cfg,
        EvolutionConfig(
            generations=args.generations,
            population=args.population,
            budget_calls=args.budget,
            seed=args.seed,
        ),
        log=EventLog(log_path),
        mutator=active_mutator,
    )
    target = report.write(args.out)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    print(f"\n报告: {target}")
    print(f"事件日志: {log_path}")
    if args.compare_runs > 0:
        comparison = compare_search(
            seed,
            benches,
            cfg,
            EvolutionConfig(
                generations=args.generations,
                population=args.population,
                budget_calls=args.budget,
                seed=args.seed,
            ),
            runs=args.compare_runs,
            seeds_per_run=args.seeds_per_run,
            mutator=active_mutator,
        )
        print("\n进化 vs 随机搜索：")
        print(json.dumps(comparison.as_dict(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agh", description="AGH 多智能体整体重构框架")
    parser.add_argument("--version", action="version", version=f"AGH {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="跑 M0 垂直切片")
    run.add_argument("--root", type=Path, default=None)
    run.add_argument("--out", type=Path, default=None)
    run.add_argument("--refresh-anchor", action="store_true")
    run.add_argument("--no-dissent", action="store_true")
    run.add_argument("--no-approve", action="store_true")
    run.set_defaults(func=cmd_run)

    verify = sub.add_parser("verify", help="校验事件日志哈希链")
    verify.add_argument("--run-dir", type=Path, default=Path("runs") / "m0")
    verify.set_defaults(func=cmd_verify)

    replay = sub.add_parser("replay", help="L1 逐位重放")
    replay.add_argument("--run-dir", type=Path, default=Path("runs") / "m0")
    replay.set_defaults(func=cmd_replay)

    experiment = sub.add_parser("experiment", help="G1 竞技场实验")
    experiment.add_argument("--seeds", type=int, default=100)
    experiment.add_argument("--resamples", type=int, default=2_000)
    experiment.add_argument("--frozen", type=Path, default=None)
    experiment.add_argument("--out", type=Path, default=Path("runs") / "g1" / "experiment.json")
    experiment.set_defaults(func=cmd_experiment)

    ablation = sub.add_parser("ablation", help="9 组消融")
    ablation.add_argument("--seeds", type=int, default=50)
    ablation.add_argument("--resamples", type=int, default=2_000)
    ablation.add_argument("--frozen", type=Path, default=None)
    ablation.add_argument("--out", type=Path, default=Path("runs") / "g1" / "ablation.json")
    ablation.set_defaults(func=cmd_ablation)

    evolve_cmd = sub.add_parser("evolve", help="档案式自我迭代（受限基因组）")
    evolve_cmd.add_argument("--root", type=Path, default=None)
    evolve_cmd.add_argument("--refresh-anchor", action="store_true")
    evolve_cmd.add_argument("--generations", type=int, default=5)
    evolve_cmd.add_argument("--population", type=int, default=3)
    evolve_cmd.add_argument("--budget", type=int, default=500)
    evolve_cmd.add_argument("--seed", type=int, default=7)
    evolve_cmd.add_argument("--out", type=Path, default=Path("runs") / "evolve" / "report.json")
    evolve_cmd.add_argument("--compare-runs", type=int, default=0, help="跑进化 vs 基线对照")
    evolve_cmd.add_argument("--seeds-per-run", type=int, default=1, help="每轮取多个种子的均值")
    evolve_cmd.add_argument("--benchmarks", type=int, default=0, help="生成多少个随机基准（0=用默认 3 个）")
    evolve_cmd.add_argument("--bench-seed", type=int, default=0)
    evolve_cmd.add_argument("--llm-mutator", action="store_true", help="用模型提议变异")
    evolve_cmd.add_argument("--provider", default="deepseek")
    evolve_cmd.add_argument("--model", default=None)
    evolve_cmd.add_argument("--api-key-env", default=None)
    evolve_cmd.set_defaults(func=cmd_evolve)

    version = sub.add_parser("version", help="打印版本")
    version.set_defaults(func=lambda _a: print(__version__) or 0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args = parser.parse_args(["run", *(argv or [])])
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
