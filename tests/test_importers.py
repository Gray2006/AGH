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


def test_failed_import_keeps_existing_log(tmp_path: Path) -> None:
    """导入失败不能毁掉上一次的结果：0 条时原日志必须原样保留。"""
    out = tmp_path / "out.jsonl"
    import_jsonl(_src(tmp_path), out)
    before = EventLog(out)
    before.verify()
    head_before = before.head()

    bad = tmp_path / "bad.jsonl"
    bad.write_text('not json\n{"x": 1}\n', encoding="utf-8")
    result = import_jsonl(bad, out)

    assert result.imported == 0
    assert result.skipped == 2
    after = EventLog(out)
    after.verify()
    assert after.head() == head_before
    assert len([e for e in after.entries if e.type == "llm.call"]) == 2


def test_failed_import_cli_keeps_existing_log(tmp_path: Path) -> None:
    from agh.cli import main

    out = tmp_path / "cli.jsonl"
    assert main(["import", "--from-jsonl", str(_src(tmp_path)), "--out", str(out)]) == 0
    head_before = EventLog(out).head()

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"foo": "bar"}\n', encoding="utf-8")
    assert main(["import", "--from-jsonl", str(bad), "--out", str(out)]) == 2
    assert EventLog(out).head() == head_before


def test_import_leaves_no_temp_file(tmp_path: Path) -> None:
    out = tmp_path / "out.jsonl"
    import_jsonl(_src(tmp_path), out)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_map_with_non_generic_format_is_an_error(tmp_path: Path) -> None:
    """--map 只对 generic 生效，静默忽略会让用户以为映射已应用。"""
    import pytest

    src = tmp_path / "langfuse.jsonl"
    src.write_text(
        json.dumps({"type": "generation", "input": "q", "output": "a", "model": "m"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="generic"):
        import_any(src, tmp_path / "out.jsonl", mapping=parse_map(["prompt=question"]))


def test_zero_import_with_corrupt_existing_log_does_not_raise(tmp_path: Path) -> None:
    """原日志已损坏时，0 条导入仍应正常返回，而不是抛 LogTampered。"""
    out = tmp_path / "out.jsonl"
    out.write_text('{"seq": 1, "broken": true}\n', encoding="utf-8")
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"foo": "bar"}\n', encoding="utf-8")
    result = import_jsonl(bad, out)
    assert result.imported == 0
    assert result.log_head == ""


def test_import_accepts_gbk_source(tmp_path: Path) -> None:
    """Windows 工具导出的日志常是 GBK，不能直接崩 UnicodeDecodeError。"""
    src = tmp_path / "gbk.jsonl"
    row = {"model": "gpt-4o", "prompt": "你好，总结一下", "response": "好的", "tokens": 12}
    src.write_bytes((json.dumps(row, ensure_ascii=False) + "\n").encode("gbk"))

    result = import_jsonl(src, tmp_path / "out.jsonl")
    assert result.imported == 1
    assert result.skipped == 0


def test_import_accepts_utf8_bom_source(tmp_path: Path) -> None:
    """记事本另存为会加 BOM；不处理的话第一行解析失败、静默导入 0 条。"""
    src = tmp_path / "bom.jsonl"
    row = {"model": "m", "prompt": "p", "response": "r", "tokens": 5}
    src.write_bytes(b"\xef\xbb\xbf" + (json.dumps(row) + "\n").encode("utf-8"))

    result = import_jsonl(src, tmp_path / "out.jsonl")
    assert result.imported == 1
    assert result.skipped == 0


def test_import_undecodable_source_raises_value_error(tmp_path: Path) -> None:
    """既不是 UTF-8 也不是 GBK 时给明确提示，而不是 UnicodeDecodeError。"""
    import pytest

    src = tmp_path / "latin1.jsonl"
    src.write_bytes(b'{"model": "m", "prompt": "caf\xe9 \xff\xfe"}\n')
    with pytest.raises(ValueError, match="UTF-8"):
        import_jsonl(src, tmp_path / "out.jsonl")


def test_import_cli_undecodable_source_exits_cleanly(tmp_path: Path) -> None:
    """CLI 层不该把 Python 堆栈甩给用户。"""
    from agh.cli import main

    src = tmp_path / "latin1.jsonl"
    src.write_bytes(b'{"model": "m", "prompt": "caf\xe9 \xff\xfe"}\n')
    assert main(["import", "--from-jsonl", str(src), "--out", str(tmp_path / "o.jsonl")]) == 2


def test_import_cli_bad_map_exits_cleanly(tmp_path: Path) -> None:
    from agh.cli import main

    src = _src(tmp_path)
    assert (
        main(
            [
                "import",
                "--from-jsonl",
                str(src),
                "--out",
                str(tmp_path / "o.jsonl"),
                "--map",
                "nonsense=field",
            ]
        )
        == 2
    )
