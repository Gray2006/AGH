"""独立监督者进程：唯一有权切换版本的角色。

它和被测代码分属不同进程，被改的代码拿不到它的内存、也改不到它的判断逻辑
（前提是权限隔离：监督者进程的文件与指针目录对子进程只读）。

协议是文件式的，简单到不会成为新的攻击面：
- 请求：`<store>/request.json`，形如 {"action": "promote", "version": "v2"}
- 处理：提取候选 → 跑 gate → 通过才停旧子进程、切指针、起新子进程
- 失败：不动现网，记录原因；请求文件删除

命令行：
    python -m agh.supervisor --store runs/selfmod -- python -m agh run
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .eventlog import EventLog
from .selfmod import ArtifactStore, Gate, PromoteResult, promote

REQUEST = "request.json"


class Child(Protocol):
    pid: int

    def alive(self) -> bool: ...

    def stop(self) -> None: ...


class ProcessChild:
    def __init__(self, command: Sequence[str], cwd: Path, env: dict[str, str] | None = None) -> None:
        self._proc = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env={**os.environ, **(env or {})},
        )

    @property
    def pid(self) -> int:
        return self._proc.pid

    def alive(self) -> bool:
        return self._proc.poll() is None

    def stop(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)


@dataclass
class SupervisorConfig:
    health_seconds: float = 1.0
    poll_seconds: float = 0.5
    max_restarts: int = 3


@dataclass
class Supervisor:
    store: ArtifactStore
    command: Sequence[str]
    gates: Sequence[Gate] = ()
    config: SupervisorConfig = field(default_factory=SupervisorConfig)
    spawn: Callable[[Sequence[str], Path, dict[str, str]], Child] = ProcessChild  # type: ignore[assignment]
    log: EventLog | None = None
    _child: Child | None = None
    _workdir: Path | None = None
    _started_version: str | None = None
    _restarts: int = 0

    # ------------------------------------------------------------ 子进程
    @property
    def current_version(self) -> str | None:
        return self._started_version

    def _spawn_version(self, version: str) -> None:
        artifact = self.store.load(version)
        workdir = self.store.extract(artifact)
        child = self.spawn(self.command, workdir, {"AGH_VERSION": version})
        deadline = time.time() + self.config.health_seconds
        while time.time() < deadline:
            if not child.alive():
                raise RuntimeError(f"{version} 启动后立即退出")
            time.sleep(0.05)
        self._child = child
        self._workdir = workdir
        self._started_version = version

    def start(self) -> str:
        current = self.store.current()
        if current is None:
            raise RuntimeError("没有已激活的版本")
        self._spawn_version(current.version)
        assert self._child is not None
        self._record("supervisor.start", {"version": current.version, "pid": self._child.pid})
        return current.version

    def stop(self) -> None:
        if self._child is not None:
            self._child.stop()
            self._record("supervisor.stop", {"version": self._started_version})
        self._child = None
        self._started_version = None

    # ------------------------------------------------------------ 切换
    def promote(self, version: str) -> PromoteResult:
        if not self.gates:
            raise RuntimeError("没有配置 gate，拒绝切换")
        result = promote(self.store, version, self.gates)
        self._record(
            "supervisor.promote",
            {
                "version": version,
                "ok": result.ok,
                "gates": [{"name": g.name, "passed": g.passed, "detail": g.detail[:300]} for g in result.gates],
            },
        )
        if not result.ok:
            return result
        previous = self._started_version
        self.stop()
        try:
            self._spawn_version(version)
        except Exception as exc:
            # 新版本起不来：指针回滚，恢复旧版本
            self.store.rollback()
            if previous:
                self._spawn_version(previous)
            self._record("supervisor.rollback", {"from": version, "to": previous, "reason": str(exc)})
            raise
        return result

    def rollback(self) -> str | None:
        previous = self.store.rollback()
        if previous is None:
            return None
        assert previous is not None
        self.stop()
        self._spawn_version(previous.version)
        self._record("supervisor.rollback", {"to": previous.version})
        return previous.version

    # ------------------------------------------------------------ 请求循环
    def request(self, action: str, version: str | None = None) -> Path:
        target = self.store.root / REQUEST
        payload = {"action": action, "version": version, "at_ms": int(time.time() * 1000)}
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, target)
        return target

    def tick(self) -> dict[str, Any] | None:
        path = self.store.root / REQUEST
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)
        action = payload.get("action")
        version = payload.get("version")
        if action == "promote" and version:
            result = self.promote(version)
            return {"action": action, "version": version, "ok": result.ok}
        if action == "rollback":
            target = self.rollback()
            return {"action": action, "version": target, "ok": target is not None}
        return {"action": action, "ok": False, "error": "未知请求"}

    def serve(self, *, duration: float | None = None) -> None:
        deadline = time.time() + duration if duration else None
        try:
            while deadline is None or time.time() < deadline:
                self.tick()
                if self._child is not None and not self._child.alive():
                    self._restarts += 1
                    if self._restarts > self.config.max_restarts:
                        raise RuntimeError("子进程反复退出，监督者停止重启")
                    self._record("supervisor.restart", {"version": self._started_version})
                    self.stop()
                    if self.store.current():
                        self._spawn_version(self.store.current().version)
                time.sleep(self.config.poll_seconds)
        finally:
            self.stop()

    # ------------------------------------------------------------ 日志
    def _record(self, kind: str, payload: dict[str, Any]) -> None:
        if self.log is not None:
            self.log.append(kind, payload)


__all__ = ["REQUEST", "Child", "ProcessChild", "Supervisor", "SupervisorConfig"]


def _cli(argv: list[str] | None = None) -> int:
    import argparse
    import shlex

    from .selfmod import CommandGate

    parser = argparse.ArgumentParser(prog="agh.supervisor", description="AGH 独立监督者")
    parser.add_argument("--store", type=Path, required=True, help="制品库目录")
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--gate", action="append", default=[], help="门禁命令，可重复")
    parser.add_argument("--health-seconds", type=float, default=1.0)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--duration", type=float, default=None, help="运行多久后退出，默认一直跑")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- 之后是子进程命令")
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("需要子进程命令，例如 -- python -m agh run")

    gates = [CommandGate(f"cmd-{i}", shlex.split(g)) for i, g in enumerate(args.gate)]
    log_path = args.log or (args.store / "supervisor.jsonl")
    supervisor = Supervisor(
        store=ArtifactStore(args.store),
        command=command,
        gates=gates,
        config=SupervisorConfig(health_seconds=args.health_seconds, poll_seconds=args.poll_seconds),
        log=EventLog(log_path),
    )
    version = supervisor.start()
    print(f"监督者已启动，当前版本 {version}")
    supervisor.serve(duration=args.duration)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
