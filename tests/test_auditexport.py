from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from agh.audit import AuditSession
from agh.auditexport import FIELDS, export_csv, export_jsonl_hash_only


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "run.jsonl"
    audit = AuditSession(path)
    audit.call(model="a", prompt="p1", response="r1", tokens=10)
    cid = audit.call(model="b", prompt="p2", response="r2", tokens=20)
    audit.flag(cid, reason="wrong", note="边界")
    return path


def test_csv_has_header_and_rows(tmp_path: Path) -> None:
    text = export_csv(_log(tmp_path))
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 2
    assert set(rows[0]) == set(FIELDS)
    flagged = [r for r in rows if r["flagged"] == "yes"]
    assert len(flagged) == 1
    assert flagged[0]["flag_reason"] == "wrong"


def test_csv_does_not_leak_payload(tmp_path: Path) -> None:
    text = export_csv(_log(tmp_path))
    assert "p1" not in text
    assert "r1" not in text


def test_csv_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "calls.csv"
    export_csv(_log(tmp_path), out)
    assert out.exists()
    assert "call_id" in out.read_text(encoding="utf-8")


def test_hashonly_export_removes_payload(tmp_path: Path) -> None:
    out = tmp_path / "hash.jsonl"
    n = export_jsonl_hash_only(_log(tmp_path), out)
    assert n == 4  # 2 calls + 1 flag + session.start
    text = out.read_text(encoding="utf-8")
    assert "p1" not in text
    assert "prompt_sha256" in text


def test_cli_export_csv(tmp_path: Path, capsys) -> None:
    from agh.cli import main

    out = tmp_path / "x.csv"
    assert main(["audit-export", "--log", str(_log(tmp_path)), "--out", str(out)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["format"] == "csv"
    assert out.exists()
