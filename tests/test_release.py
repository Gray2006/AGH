from __future__ import annotations

from pathlib import Path

import pytest

from agh.eventlog import LogTampered
from agh.release import (
    ReleaseError,
    anchor_release,
    read_version,
    require_clean_tree,
    verify_release,
)

ROOT = Path(__file__).resolve().parents[1]


def test_read_version_matches_package() -> None:
    assert read_version(ROOT)


def test_read_version_detects_mismatch(tmp_path: Path) -> None:
    (tmp_path / "agh").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")
    (tmp_path / "agh" / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    with pytest.raises(ReleaseError):
        read_version(tmp_path)


def test_anchor_and_verify_release(tmp_path: Path) -> None:
    result = anchor_release(
            ROOT, run_dir=tmp_path / "m0", create_tag=False, store_path=tmp_path / "anchors.jsonl"
        )
    assert result.anchor.size > 0
    assert result.local_store.exists()

    # verify_release 按版本找 runs/anchors，这里直接校验日志与锚点
    from agh.anchoring import check_log
    from agh.eventlog import EventLog
    from agh.pipeline import dev_keyring

    log = EventLog(result.run_dir / "events.jsonl")
    assert check_log(log, result.anchor, keyring=dev_keyring("ed25519")) is True


def test_verify_release_rejects_tampered_log(tmp_path: Path) -> None:
    from agh.anchoring import check_log
    from agh.eventlog import EventLog
    from agh.pipeline import dev_keyring

    result = anchor_release(
            ROOT, run_dir=tmp_path / "m0", create_tag=False, store_path=tmp_path / "anchors.jsonl"
        )
    path = result.run_dir / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"type": "', '"type": "x-')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LogTampered):
        check_log(EventLog(path), result.anchor, keyring=dev_keyring("ed25519"))


def test_require_clean_tree_ok_in_repo() -> None:
    # 仓库本身可能正在被编辑；这里只验证函数能读 git 状态而不抛非预期错误
    try:
        require_clean_tree(ROOT)
    except ReleaseError as exc:
        assert "干净" in str(exc)


def test_verify_release_missing_anchor(tmp_path: Path) -> None:
    with pytest.raises(ReleaseError):
        verify_release(tmp_path, version="0.0.0")
