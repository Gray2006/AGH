from __future__ import annotations

import json
from pathlib import Path

from agh.eventlog import EventLog
from agh.importers import import_jsonl, parse_map


def _src(tmp_path: Path) -> Path:
    path = tmp_path / "my_log.jsonl"
    rows = [
        {"model": "deepseek-chat", "prompt": "p1", "response": "r1", "tokens": 10},
        {"model": "deepseek-chat", "prompt": "p2", "response": "r2", "tokens": 20},
        {"model": "", "prompt": "bad", "response": "x"},  # 缺 model → 跳过
        {"prompt": "no model", "response": "x"},  # 缺 model → 跳过
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def test_import_jsonl_writes_verifiable_log(tmp_path: Path) -> None:
    result = import_jsonl(_src(tmp_path), tmp_path / "out.jsonl")
    assert result.imported == 2
    assert result.skipped == 2
    log = EventLog(tmp_path / "out.jsonl")
    log.verify()  # 不抛即通过
    calls = [e for e in log.entries if e.type == "llm.call"]
    assert len(calls) == 2
    assert calls[0].payload["tokens"] == 10


def test_import_jsonl_custom_mapping(tmp_path: Path) -> None:
    src = tmp_path / "other.jsonl"
    src.write_text(
        json.dumps({"model_name": "m", "input_text": "in", "output_text": "out"}, ensure_ascii=False),
        encoding="utf-8",
    )
    mapping = parse_map(
        ["model=model_name", "prompt=input_text", "response=output_text"]
    )
    result = import_jsonl(src, tmp_path / "out.jsonl", mapping=mapping)
    assert result.imported == 1
    log = EventLog(tmp_path / "out.jsonl")
    call = next(e for e in log.entries if e.type == "llm.call")
    assert call.payload["prompt"] == "in"
    assert call.payload["response"] == "out"


def test_parse_map_rejects_unknown_key() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse_map(["nope=x"])


def test_import_skips_malformed_lines(tmp_path: Path) -> None:
    src = tmp_path / "broken.jsonl"
    src.write_text(
        '{"model":"m","prompt":"p","response":"r"}\nnot json\n[1,2]\n', encoding="utf-8"
    )
    result = import_jsonl(src, tmp_path / "out.jsonl")
    assert result.imported == 1
    assert result.skipped == 2


def test_import_cli(tmp_path: Path) -> None:
    from agh.cli import main

    src = _src(tmp_path)
    out = tmp_path / "cli.jsonl"
    code = main(["import", "--from-jsonl", str(src), "--out", str(out)])
    assert code == 0
    assert out.exists()
    EventLog(out).verify()


def test_reimport_overwrites(tmp_path: Path) -> None:
    """重复导入同一份源不应追加出重复条目。"""
    src = _src(tmp_path)
    out = tmp_path / "out.jsonl"
    import_jsonl(src, out)
    import_jsonl(src, out)
    log = EventLog(out)
    calls = [e for e in log.entries if e.type == "llm.call"]
    assert len(calls) == 2
