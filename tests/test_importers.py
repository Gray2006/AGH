from __future__ import annotations

import json
from pathlib import Path

from agh.eventlog import EventLog
from agh.importers import import_any, import_jsonl, parse_map


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


def test_langfuse_export_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "langfuse.jsonl"
    src.write_text(
        json.dumps(
            {
                "type": "generation",
                "trace_id": "t1",
                "input": "把 [3,1,2] 排序",
                "output": "[1,2,3]",
                "model": "gpt-x",
                "usage": {"input": 10, "output": 5},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = import_any(src, tmp_path / "out.jsonl")
    assert result.detected_format == "langfuse"
    assert result.imported == 1
    log = EventLog(result.out)
    call = next(e for e in log.entries if e.type == "llm.call")
    assert call.payload["model"] == "gpt-x"
    assert call.payload["tokens"] == 15
    assert "排序" in call.payload["prompt"]


def test_langsmith_export_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "langsmith.jsonl"
    src.write_text(
        json.dumps(
            {
                "run_type": "llm",
                "inputs": {"messages": [{"role": "user", "content": "什么是哈希链"}]},
                "outputs": {
                    "messages": [{"role": "assistant", "content": "一种链式结构"}],
                    "token_usage": {"prompt_tokens": 7, "completion_tokens": 3},
                },
                "extra": {"metadata": {"ls_model_name": "claude-x"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = import_any(src, tmp_path / "out.jsonl")
    assert result.detected_format == "langsmith"
    log = EventLog(result.out)
    call = next(e for e in log.entries if e.type == "llm.call")
    assert call.payload["model"] == "claude-x"
    assert call.payload["prompt"] == "什么是哈希链"
    assert call.payload["response"] == "一种链式结构"
    assert call.payload["tokens"] == 10


def test_langsmith_skips_non_llm_runs(tmp_path: Path) -> None:
    src = tmp_path / "ls.jsonl"
    src.write_text(
        "\n".join(
            [
                json.dumps({"run_type": "chain", "inputs": {"a": 1}, "outputs": {"b": 2}}),
                json.dumps(
                    {
                        "run_type": "llm",
                        "inputs": {"messages": [{"content": "q"}]},
                        "outputs": {"messages": [{"content": "a"}]},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    result = import_any(src, tmp_path / "out.jsonl")
    assert result.imported == 1
    assert result.skipped == 1


def test_format_flag_overrides_detection(tmp_path: Path) -> None:
    src = tmp_path / "x.jsonl"
    src.write_text(json.dumps({"model": "m", "prompt": "p", "response": "r"}), encoding="utf-8")
    result = import_any(src, tmp_path / "out.jsonl", fmt="generic")
    assert result.detected_format == "generic"
    assert result.imported == 1


def test_import_zero_records_is_an_error(tmp_path: Path) -> None:
    """一条都没导进来时不能返回成功。"""
    from agh.cli import main

    src = tmp_path / "unknown.jsonl"
    src.write_text('{"foo": "bar"}\n{"baz": 1}\n', encoding="utf-8")
    code = main(["import", "--from-jsonl", str(src), "--out", str(tmp_path / "o.jsonl")])
    assert code == 2


def test_import_openai_format(tmp_path: Path) -> None:
    """OpenAI chat completion 响应：choices[0].message.content。"""
    src = tmp_path / "openai.jsonl"
    src.write_text(
        json.dumps(
            {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
                "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                "usage": {"total_tokens": 12},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = import_jsonl(src, tmp_path / "out.jsonl")
    assert result.imported == 1
    log = EventLog(tmp_path / "out.jsonl")
    call = next(e for e in log.entries if e.type == "llm.call")
    assert call.payload["model"] == "gpt-4o"
    assert call.payload["prompt"] == "hi"
    assert call.payload["response"] == "hello"
    assert call.payload["tokens"] == 12
