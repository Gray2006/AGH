"""路径边界：含中文、空格、Unicode 的目录名。

Windows 用户的路径经常带中文（比如 `G:\\工作区\\AGH`），这类问题在 Linux CI 上不会暴露。
"""

from __future__ import annotations

import json
from pathlib import Path

from agh.cli import main


def test_quickstart_in_chinese_path(tmp_path: Path, capsys) -> None:
    target = tmp_path / "中文 路径 test"
    assert main(["quickstart", "--dir", str(target)]) == 0
    assert (target / "run.jsonl").exists()
    assert (target / "report.html").exists()


def test_verify_in_chinese_path(tmp_path: Path, capsys) -> None:
    target = tmp_path / "带空格的 目录"
    main(["quickstart", "--dir", str(target)])
    capsys.readouterr()
    assert main(["audit", "verify", "--log", str(target / "run.jsonl")]) == 0


def test_ui_and_export_in_chinese_path(tmp_path: Path, capsys) -> None:
    target = tmp_path / "中文 α β"
    main(["quickstart", "--dir", str(target)])
    capsys.readouterr()

    out = target / "报告.html"
    assert main(["ui", "--log", str(target / "run.jsonl"), "--out", str(out), "--no-open"]) == 0
    assert out.exists()

    csv_path = target / "数据.csv"
    assert main(["audit-export", "--log", str(target / "run.jsonl"), "--out", str(csv_path)]) == 0
    assert csv_path.exists()
    assert "call_id" in csv_path.read_text(encoding="utf-8")


def test_import_from_chinese_path(tmp_path: Path, capsys) -> None:
    src = tmp_path / "源 日志.jsonl"
    src.write_text(
        json.dumps({"model": "m", "prompt": "p", "response": "r"}, ensure_ascii=False),
        encoding="utf-8",
    )
    out = tmp_path / "导入 后.jsonl"
    assert main(["import", "--from-jsonl", str(src), "--out", str(out)]) == 0
    assert out.exists()
