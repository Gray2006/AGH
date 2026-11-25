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
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .anchoring import AnchorStore, anchor_log
from .autonomous import AutonomousConfig, run_autonomous
from .crypto import KeyRing
from .eventlog import EventLog
from .evolution import EvolutionConfig, Strategy, default_benchmarks, evolve
from .evolution_llm import compare_search
from .frozen import FrozenLayer
from .pipeline import DEV_KID, DEV_SECRET, PARENT_SIG, dev_keyring, faithful_child, m0_skeleton, run_m0
from .report import collect, render
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


def _require_file(path: str | Path, what: str = "日志") -> Path:
    target = Path(path)
    if not target.exists():
        raise SystemExit(f"找不到{what}：{target}")
    if not target.is_file():
        raise SystemExit(f"{what}不是文件：{target}")
    return target


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
        key_kind=args.sign,
    )
    if args.anchor_store:
        log = EventLog(run_dir / "events.jsonl")
        key = dev_keyring("ed25519").get(DEV_KID)
        anchor = anchor_log(log, key=key, label="m0")
        AnchorStore(args.anchor_store).append(anchor)
        print(f"anchor: {args.anchor_store} head={anchor.head[:12]}")
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
    if args.mode == "meta":
        from .meta import meta_evolve

        result = meta_evolve(
            cfg,
            EvolutionConfig(
                generations=args.generations,
                population=args.population,
                budget_calls=args.budget,
                seed=args.seed,
            ),
            rounds=args.rounds,
        )
        target = result.write(args.out)
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        print(f"\n报告: {target}")
        return 0

    if args.mode in ("sharded", "combined"):
        from .evolution_sharded import combined_evolve, sharded_evolve

        evo_config = EvolutionConfig(
            generations=args.generations,
            population=args.population,
            budget_calls=args.budget,
            seed=args.seed,
        )
        result: Any
        if args.mode == "sharded":
            result = sharded_evolve(benches, cfg, evo_config, mutator=active_mutator)
        else:
            result = combined_evolve(benches, cfg, evo_config, rounds=args.rounds)
        target = result.write(args.out)
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        print(f"\n报告: {target}")
        return 0

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


def cmd_daemon(args: argparse.Namespace) -> int:
    root = (args.root or repo_root()).resolve()
    frozen = root / "config" / "frozen"
    log_path = args.out
    log_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_autonomous(
        frozen,
        AutonomousConfig(
            rounds=args.rounds,
            generations=args.generations,
            population=args.population,
            benchmarks=args.benchmarks,
            patience=args.patience,
            write_back=not args.no_write_back,
            seed=args.seed,
            llm_mutator=args.llm_mutator,
            provider=args.provider,
            model=args.model,
            api_key_env=args.api_key_env,
            daily_token_budget=args.daily_budget,
            seed_degrade=args.seed_drop,
            hide_gold=args.hide_gold,
            replay_mutations=args.replay_mutations,
            failures=args.failures,
            family=args.family,
        ),
        log=EventLog(log_path),
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    payload = collect(args.runs)
    print(render(payload))
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
    run.add_argument("--sign", choices=["hmac", "ed25519"], default="hmac")
    run.add_argument(
        "--anchor-store",
        default=None,
        help="把本次事件日志的链头写进锚点存储（日志之外的独立文件），用于发现整链替换",
    )
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
    evolve_cmd.add_argument("--mode", choices=["single", "sharded", "combined", "meta"], default="single")
    evolve_cmd.add_argument("--rounds", type=int, default=3)
    evolve_cmd.add_argument("--llm-mutator", action="store_true", help="用模型提议变异")
    evolve_cmd.add_argument("--provider", default="deepseek")
    evolve_cmd.add_argument("--model", default=None)
    evolve_cmd.add_argument("--api-key-env", default=None)
    evolve_cmd.set_defaults(func=cmd_evolve)

    daemon = sub.add_parser("daemon", help="自主迭代：进化 → 门禁 → 回写冻结层")
    daemon.add_argument("--root", type=Path, default=None)
    daemon.add_argument("--rounds", type=int, default=4)
    daemon.add_argument("--generations", type=int, default=2)
    daemon.add_argument("--population", type=int, default=2)
    daemon.add_argument("--benchmarks", type=int, default=6)
    daemon.add_argument("--patience", type=int, default=2)
    daemon.add_argument("--seed", type=int, default=0)
    daemon.add_argument("--no-write-back", action="store_true")
    daemon.add_argument("--llm-mutator", action="store_true")
    daemon.add_argument("--provider", default="deepseek")
    daemon.add_argument("--model", default=None)
    daemon.add_argument("--api-key-env", default=None)
    daemon.add_argument("--daily-budget", type=int, default=0, help="token 预算，0 不限")
    daemon.add_argument(
        "--seed-drop",
        type=float,
        default=0.0,
        help="把种子策略的边/必需项随机抽掉这个比例（0-0.9），制造可爬的梯度",
    )
    daemon.add_argument(
        "--hide-gold",
        action="store_true",
        help="信息降质：变异器只看得到降质后保留的边，缺的边得靠推断（默认给全集）",
    )
    daemon.add_argument(
        "--family",
        choices=["default", "hard", "wide", "deep"],
        default="default",
        help="skeleton family: bigger/denser graphs with stricter vertical moves",
    )
    daemon.add_argument(
        "--failures",
        default=None,
        help="real failure fixtures: evolve from a model's wrong reconstruction back toward the seed",
    )
    daemon.add_argument(
        "--replay-mutations",
        default=None,
        help="L1 重放：从事件日志读 llm.mutation 记录，不调用模型，逐位复现进化轨迹",
    )
    daemon.add_argument("--out", type=Path, default=Path("runs") / "daemon" / "events.jsonl")
    daemon.set_defaults(func=cmd_daemon)

    report = sub.add_parser("report", help="汇总 runs/ 下的实验结果")
    report.add_argument("--runs", type=Path, default=Path("runs"))
    report.set_defaults(func=cmd_report)


    anchor = sub.add_parser("anchor", help="事件日志外部锚定：写链头 / 校验是否被替换")
    anchor.add_argument("--events", required=True)
    anchor.add_argument("--store", default=None)
    anchor.add_argument(
        "--store-git",
        default=None,
        help="use git tags as the anchor store (the remote becomes the external location)",
    )
    anchor.add_argument("--label", default="")
    anchor.add_argument("--sign", choices=["none", "ed25519"], default="ed25519")
    anchor.add_argument("--verify", action="store_true")
    anchor.set_defaults(func=cmd_anchor)
    audit = sub.add_parser("audit", help="审计日志：摘要 / 校验 / 导出失败样本")
    audit.add_argument("action", choices=["summary", "verify", "export-failures"])
    audit.add_argument("--log", required=True)
    audit.add_argument("--out", default=None)
    audit.add_argument("--no-payload", action="store_true", help="导出时不带原文")
    audit.set_defaults(func=cmd_audit)
    feedback = sub.add_parser("feedback", help="把审计日志整理成可粘贴的反馈")
    feedback.add_argument("--log", required=True)
    feedback.add_argument("--out", default=None)
    feedback.add_argument("--with-payload", action="store_true", help="带上输入输出原文（默认脱敏）")
    feedback.set_defaults(func=cmd_feedback)
    quickstart = sub.add_parser("quickstart", help="30 秒看完审计链路（不需要 key）")
    quickstart.add_argument("--dir", default=None, help="产物目录，默认 ./agh-quickstart")
    quickstart.set_defaults(func=cmd_quickstart)
    ui = sub.add_parser("ui", help="把审计日志渲染成自包含 HTML 报告")
    ui.add_argument("--log", default=None)
    ui.add_argument("--from-run", action="store_true", help="读 ./agh-quickstart/run.jsonl")
    ui.add_argument("--out", default=None)
    ui.add_argument("--no-open", action="store_true", help="只生成，不自动打开浏览器")
    ui.add_argument("--max-calls", type=int, default=None, help="最多渲染多少条调用（大日志防卡）")
    ui.set_defaults(func=cmd_ui)
    imp = sub.add_parser("import", help="把已有 jsonl 日志搬进可验证格式")
    imp.add_argument("--from-jsonl", required=True)
    imp.add_argument("--out", default=None)
    imp.add_argument(
        "--format",
        choices=["auto", "generic", "langfuse", "langsmith"],
        default="auto",
        help="源日志格式；auto 按第一行判断",
    )
    imp.add_argument(
        "--map",
        action="append",
        default=None,
        help="字段映射，例如 --map prompt=input_text --map response=output_text",
    )
    imp.set_defaults(func=cmd_import)
    audit_diff = sub.add_parser("audit-diff", help="比较两份审计日志")
    audit_diff.add_argument("--a", required=True)
    audit_diff.add_argument("--b", required=True)
    audit_diff.set_defaults(func=cmd_audit_diff)
    doctor = sub.add_parser("doctor", help="环境自检")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)
    version = sub.add_parser("version", help="打印版本")
    version.set_defaults(func=lambda _a: print(__version__) or 0)

    return parser


def cmd_anchor(args: argparse.Namespace) -> int:
    log = EventLog(Path(args.events))
    if args.store_git:
        from .anchoring import GitTagStore

        store = GitTagStore(args.store_git)  # type: ignore[assignment]
    elif args.store:
        store = AnchorStore(args.store)
    else:
        raise SystemExit("需要 --store 或 --store-git")
    if args.verify:
        keyring = dev_keyring("ed25519") if args.sign == "ed25519" else None
        anchored = store.check(log, keyring=keyring)
        print(
            json.dumps(
                {
                    "ok": True,
                    "log": str(log.path),
                    "head": log.head(),
                    "size": log.size(),
                    "signature_verified": anchored,
                },
                ensure_ascii=False,
            )
        )
        return 0
    key = dev_keyring("ed25519").get(DEV_KID) if args.sign == "ed25519" else None
    anchor = anchor_log(log, key=key, label=args.label)
    store.append(anchor)
    print(json.dumps(anchor.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from .audit import AuditSession, export_failures

    _require_file(args.log)
    if args.action == "summary":
        audit = AuditSession.__new__(AuditSession)
        audit.path = Path(args.log)
        audit.log = EventLog(Path(args.log))
        print(json.dumps(audit.summary(), ensure_ascii=False, indent=2))
        return 0
    if args.action == "verify":
        EventLog(Path(args.log)).verify()
        print(json.dumps({"ok": True, "log": args.log}, ensure_ascii=False))
        return 0
    if args.action == "export-failures":
        out = Path(args.out or Path(args.log).with_suffix(".failures.json"))
        count = export_failures(args.log, out, include_payload=not args.no_payload)
        print(json.dumps({"ok": True, "cases": count, "out": str(out)}, ensure_ascii=False))
        return 0
    raise SystemExit(f"未知 action: {args.action}")


def cmd_feedback(args: argparse.Namespace) -> int:
    from .feedback import build_feedback

    _require_file(args.log)
    text = build_feedback(args.log, with_payload=args.with_payload)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(json.dumps({"ok": True, "out": str(out)}, ensure_ascii=False))
    else:
        print(text)
    return 0


def cmd_quickstart(args: argparse.Namespace) -> int:
    from .quickstart import render_quickstart, run_quickstart

    report = run_quickstart(args.dir)
    print(render_quickstart(report))
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    import webbrowser

    from .ui import render_html

    log = args.log
    if args.from_run and args.log:
        raise SystemExit("--log 与 --from-run 只能给一个")
    if args.from_run or log is None:
        default = Path("agh-quickstart") / "run.jsonl"
        if args.from_run or default.exists():
            log = str(default)
        else:
            raise SystemExit(f"找不到 {default}，先跑一次 agh quickstart，或用 --log 指定日志")
    _require_file(log)
    out = Path(args.out) if args.out else Path(log).with_suffix(".report.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(log, max_calls=args.max_calls), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out), "log": log}, ensure_ascii=False))
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from .importers import import_any, parse_map

    _require_file(args.from_jsonl, "源日志")
    out = args.out or str(Path(args.from_jsonl).with_suffix(".agh.jsonl"))
    result = import_any(args.from_jsonl, out, fmt=args.format, mapping=parse_map(args.map))
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_audit_diff(args: argparse.Namespace) -> int:
    from .auditdiff import diff_logs

    _require_file(args.a, "日志 A")
    _require_file(args.b, "日志 B")
    diff = diff_logs(args.a, args.b)
    print(json.dumps(diff.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import render, run_doctor

    report = run_doctor()
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    from .eventlog import LogTampered

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args = parser.parse_args(["run", *(argv or [])])
    try:
        return int(args.func(args))
    except LogTampered as exc:
        # 校验失败是预期内的结论，不该以 traceback 的形式甩给用户
        print(f"日志校验失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
