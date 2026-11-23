from __future__ import annotations

from pathlib import Path

import pytest

from agh.selfmod import (
    ArtifactStore,
    CallableGate,
    SelfModError,
    build_manifest,
    promote,
)


def make_version(tmp_path: Path, name: str, content: str = "x") -> Path:
    src = tmp_path / f"src-{name}"
    src.mkdir()
    (src / "mod.py").write_text(f"VALUE = {content!r}\n", encoding="utf-8")
    return src


def test_stage_verify_and_manifest(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    artifact = store.stage(make_version(tmp_path, "v1"), "v1")
    assert store.verify(artifact)
    assert "mod.py" in artifact.manifest
    extracted = store.extract(artifact)
    assert (extracted / "mod.py").exists()


def test_tampered_archive_is_rejected(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    artifact = store.stage(make_version(tmp_path, "v1"), "v1")
    artifact.archive.write_bytes(b"not a tarball")
    assert not store.verify(artifact)
    with pytest.raises(SelfModError):
        store.extract(artifact)


def test_activate_and_rollback(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    store.stage(make_version(tmp_path, "v1"), "v1")
    store.stage(make_version(tmp_path, "v2"), "v2")
    store.activate("v1")
    store.activate("v2")
    assert store.current().version == "v2"
    previous = store.rollback()
    assert previous is not None and previous.version == "v1"
    assert store.current().version == "v1"
    assert store.rollback() is None


def test_promote_blocks_on_failed_gate(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    store.stage(make_version(tmp_path, "v1"), "v1")
    store.activate("v1")
    store.stage(make_version(tmp_path, "v2"), "v2")
    result = promote(store, "v2", [CallableGate("tests", lambda _d: (False, "测试失败"))])
    assert not result.ok
    assert not result.activated
    assert store.current().version == "v1"


def test_promote_activates_when_all_gates_pass(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    store.stage(make_version(tmp_path, "v1"), "v1")
    store.activate("v1")
    store.stage(make_version(tmp_path, "v2"), "v2")
    result = promote(
        store,
        "v2",
        [
            CallableGate("files", lambda d: (d / "mod.py").exists()),
            CallableGate("content", lambda d: "VALUE" in (d / "mod.py").read_text(encoding="utf-8")),
        ],
    )
    assert result.ok and result.activated
    assert store.current().version == "v2"


def test_gate_exception_counts_as_failure(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    store.stage(make_version(tmp_path, "v1"), "v1")
    store.activate("v1")
    store.stage(make_version(tmp_path, "v2"), "v2")

    def boom(_d: Path) -> bool:
        raise RuntimeError("gate 崩了")

    result = promote(store, "v2", [CallableGate("boom", boom)])
    assert not result.ok
    assert "异常" in result.gates[0].detail


def test_gc_keeps_current_and_recent(tmp_path: Path) -> None:
    ticks = iter(range(1, 100))
    store = ArtifactStore(tmp_path / "store", clock=lambda: next(ticks))
    for index in range(1, 5):
        store.stage(make_version(tmp_path, f"v{index}"), f"v{index}")
    store.activate("v4")
    removed = store.gc(keep_last=2, min_age_days=0, now_ms=10**12)
    assert set(removed) == {"v1", "v2"}
    assert store.current().version == "v4"
    assert (tmp_path / "store" / "v4.tar.gz").exists()


def test_manifest_stable(tmp_path: Path) -> None:
    src = make_version(tmp_path, "v1")
    assert build_manifest(src) == build_manifest(src)
