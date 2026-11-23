from __future__ import annotations

from pathlib import Path

import pytest

from agh.crypto import KeyRing
from agh.frozen import (
    FrozenLayer,
    FrozenLayerError,
    FrozenLayerTampered,
    SelfReferenceError,
    load_json,
)

SECRET = b"frozen-test"


def test_manifest_covers_config(frozen_root: Path) -> None:
    layer = FrozenLayer(frozen_root)
    manifest = layer.manifest()
    assert "thresholds.json" in manifest
    assert "risk_model.json" in manifest
    assert "phase_gates.json" in manifest
    assert "scripts/go_no_go.py" in manifest


def test_anchor_verifies(frozen_root: Path) -> None:
    layer = FrozenLayer(frozen_root)
    ring = KeyRing.with_secret("k", SECRET)
    anchor = layer.write_anchor(frozen_root.parent / "anchor.json", ring, "k")
    assert anchor.manifest_sha256
    loaded = layer.verify(frozen_root.parent / "anchor.json", ring)
    assert loaded.manifest == layer.manifest()


def test_anchor_inside_frozen_dir_rejected(frozen_root: Path) -> None:
    layer = FrozenLayer(frozen_root)
    with pytest.raises(SelfReferenceError):
        layer.write_anchor(
            frozen_root / "anchor.json", KeyRing.with_secret("k", SECRET), "k"
        )


def test_modified_frozen_file_detected(frozen_root: Path) -> None:
    ring = KeyRing.with_secret("k", SECRET)
    layer = FrozenLayer(frozen_root)
    anchor_path = frozen_root.parent / "anchor.json"
    layer.write_anchor(anchor_path, ring, "k")
    target = frozen_root / "thresholds.json"
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(FrozenLayerTampered) as exc:
        layer.verify(anchor_path, ring)
    assert exc.value.diffs["thresholds.json"] == "changed"


def test_unexpected_file_detected(frozen_root: Path) -> None:
    ring = KeyRing.with_secret("k", SECRET)
    layer = FrozenLayer(frozen_root)
    anchor_path = frozen_root.parent / "anchor.json"
    layer.write_anchor(anchor_path, ring, "k")
    (frozen_root / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FrozenLayerTampered) as exc:
        layer.verify(anchor_path, ring)
    assert exc.value.diffs["extra.json"] == "unexpected"


def test_bad_anchor_signature_detected(frozen_root: Path) -> None:
    ring = KeyRing.with_secret("k", SECRET)
    layer = FrozenLayer(frozen_root)
    anchor_path = frozen_root.parent / "anchor.json"
    layer.write_anchor(anchor_path, ring, "k")
    raw = __import__("json").loads(anchor_path.read_text(encoding="utf-8"))
    raw["sig"] = "0" * 64
    anchor_path.write_text(__import__("json").dumps(raw), encoding="utf-8")
    with pytest.raises(FrozenLayerError):
        layer.verify(anchor_path, ring)


def test_guard_write_blocks_frozen_scope(frozen_root: Path) -> None:
    layer = FrozenLayer(frozen_root)
    with pytest.raises(FrozenLayerError):
        layer.guard_write(frozen_root / "thresholds.json")
    layer.guard_write(frozen_root.parent / "elsewhere.json")


def test_load_json_reads_frozen(frozen_root: Path) -> None:
    raw = load_json(frozen_root, "thresholds.json")
    assert "arena" in raw
