from __future__ import annotations

from pathlib import Path

import pytest

from agh.selfmod import ArtifactStore, CallableGate
from agh.supervisor import Supervisor, SupervisorConfig


class FakeChild:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stopped = False

    def alive(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True


class FakeSpawner:
    def __init__(self) -> None:
        self.created: list[FakeChild] = []
        self.calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []

    def __call__(self, command, cwd, env):
        child = FakeChild(pid=len(self.created) + 1)
        self.created.append(child)
        self.calls.append((tuple(command), Path(cwd), dict(env)))
        return child


def make_store(tmp_path: Path) -> ArtifactStore:
    store = ArtifactStore(tmp_path / "store")
    for version in ("v1", "v2"):
        src = tmp_path / f"src-{version}"
        src.mkdir()
        (src / "app.py").write_text(f"VERSION = {version!r}\n", encoding="utf-8")
        store.stage(src, version)
    store.activate("v1")
    return store


def test_start_runs_current_version(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    spawner = FakeSpawner()
    sup = Supervisor(store, ["app"], spawn=spawner, config=SupervisorConfig(health_seconds=0))
    assert sup.start() == "v1"
    assert spawner.calls[0][2]["AGH_VERSION"] == "v1"


def test_promote_swaps_child_when_gates_pass(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    spawner = FakeSpawner()
    sup = Supervisor(
        store,
        ["app"],
        gates=[CallableGate("ok", lambda _d: True)],
        spawn=spawner,
        config=SupervisorConfig(health_seconds=0),
    )
    sup.start()
    old_child = sup._child
    result = sup.promote("v2")
    assert result.ok and result.activated
    assert store.current().version == "v2"
    assert old_child is not None and old_child.stopped
    assert sup.current_version == "v2"


def test_promote_keeps_old_child_when_gate_fails(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    spawner = FakeSpawner()
    sup = Supervisor(
        store,
        ["app"],
        gates=[CallableGate("fail", lambda _d: (False, "测试失败"))],
        spawn=spawner,
        config=SupervisorConfig(health_seconds=0),
    )
    sup.start()
    old = sup._child
    result = sup.promote("v2")
    assert not result.ok
    assert store.current().version == "v1"
    assert sup.current_version == "v1"
    assert old is not None and not old.stopped


def test_rollback_restores_previous(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    spawner = FakeSpawner()
    sup = Supervisor(
        store,
        ["app"],
        gates=[CallableGate("ok", lambda _d: True)],
        spawn=spawner,
        config=SupervisorConfig(health_seconds=0),
    )
    sup.start()
    sup.promote("v2")
    assert sup.rollback() == "v1"
    assert sup.current_version == "v1"


def test_tick_handles_request_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    spawner = FakeSpawner()
    sup = Supervisor(
        store,
        ["app"],
        gates=[CallableGate("ok", lambda _d: True)],
        spawn=spawner,
        config=SupervisorConfig(health_seconds=0),
    )
    sup.start()
    sup.request("promote", "v2")
    outcome = sup.tick()
    assert outcome is not None and outcome["ok"] is True
    assert store.current().version == "v2"


def test_promote_requires_gates(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    sup = Supervisor(store, ["app"], spawn=FakeSpawner())
    with pytest.raises(RuntimeError):
        sup.promote("v2")


def test_process_child_end_to_end(tmp_path: Path) -> None:
    import sys

    store = ArtifactStore(tmp_path / "store")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print(1)", encoding="utf-8")
    store.stage(src, "v1")
    store.activate("v1")
    sup = Supervisor(
        store,
        [sys.executable, "-c", "import time; time.sleep(5)"],
        config=SupervisorConfig(health_seconds=0.5),
    )
    assert sup.start() == "v1"
    assert sup._child is not None and sup._child.alive()
    sup.stop()
