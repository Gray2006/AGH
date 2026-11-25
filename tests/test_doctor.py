from __future__ import annotations

from agh.doctor import render, run_doctor


def test_doctor_reports_python_and_frozen() -> None:
    report = run_doctor()
    names = [c.name for c in report.checks]
    assert "python>=3.11" in names
    assert "frozen config" in names
    assert "model api key" in names


def test_doctor_does_not_leak_key_values(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-super-secret-value")
    report = run_doctor()
    text = render(report)
    assert "sk-super-secret-value" not in text
    assert "DEEPSEEK_API_KEY" in text


def test_doctor_render_mentions_status() -> None:
    text = render(run_doctor())
    assert "环境自检" in text
    assert "OK" in text or "FAIL" in text


def test_doctor_cli_json() -> None:
    from agh.cli import main

    code = main(["doctor", "--json"])
    assert code in (0, 1)
