from __future__ import annotations

import json
from pathlib import Path

from agh.report import collect, render


def test_collect_empty(tmp_path: Path) -> None:
    payload = collect(tmp_path)
    assert payload["rows"] == []
    assert "没有找到" in render(payload)


def test_collect_reads_experiment(tmp_path: Path) -> None:
    (tmp_path / "g1").mkdir()
    (tmp_path / "g1" / "experiment.json").write_text(
        json.dumps({"contested_rate": 1.0, "metrics": {"fact_retention": 0.7}}), encoding="utf-8"
    )
    payload = collect(tmp_path)
    assert payload["available"] == ["experiment"]
    assert "contested=1.0" in render(payload)


def test_collect_skips_broken_json(tmp_path: Path) -> None:
    (tmp_path / "g1").mkdir()
    (tmp_path / "g1" / "llm-bench.json").write_text("{not json", encoding="utf-8")
    assert collect(tmp_path)["rows"] == []


def test_collect_skips_non_utf8_file(tmp_path: Path) -> None:
    # 别的工具按 GBK 写的结果文件：跳过这一份，别让整张表崩
    (tmp_path / "m0").mkdir()
    (tmp_path / "m0" / "report.json").write_bytes('{"winner": "中文"}'.encode("gbk"))
    assert collect(tmp_path)["rows"] == []


def test_collect_skips_json_that_is_not_an_object(tmp_path: Path) -> None:
    (tmp_path / "m0").mkdir()
    (tmp_path / "m0" / "report.json").write_text('["not", "a", "dict"]', encoding="utf-8")
    assert collect(tmp_path)["rows"] == []


def test_collect_tolerates_wrong_field_types(tmp_path: Path) -> None:
    # 字段类型不对时降级取默认值，而不是抛 AttributeError
    (tmp_path / "m0").mkdir()
    (tmp_path / "m0" / "report.json").write_text(
        json.dumps({"winner": "x", "scores": [1, 2, 3]}), encoding="utf-8"
    )
    (tmp_path / "g1").mkdir()
    (tmp_path / "g1" / "ablation.json").write_text(
        json.dumps({"rows": "oops"}), encoding="utf-8"
    )
    payload = collect(tmp_path)
    by_name = {r["name"]: r for r in payload["rows"]}
    assert by_name["m0"]["score"] is None
    assert by_name["ablation"]["rows"] == 0


def test_collect_llm_rows(tmp_path: Path) -> None:
    (tmp_path / "g1").mkdir()
    (tmp_path / "g1" / "llm-hard50.json").write_text(
        json.dumps({"benchmarks": 50, "llm_mean": 0.68, "rule_mean": 0.75, "delta": {"mean": -0.06}}),
        encoding="utf-8",
    )
    payload = collect(tmp_path)
    assert payload["rows"][0]["name"] == "llm_hard_50"
    assert payload["rows"][0]["n"] == 50
