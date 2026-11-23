from __future__ import annotations

import pytest

from agh.providers import ChatClient, make_client


def fake_transport(captured: list[dict]) -> object:
    def transport(url: str, headers: dict[str, str], payload: dict) -> dict:
        captured.append({"url": url, "headers": headers, "payload": payload})
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    return transport


def test_client_builds_request_and_parses_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_KEY", "sk-test")
    captured: list[dict] = []
    client = ChatClient(
        base_url="https://api.example.com/v1",
        model="m1",
        api_key_env="TEST_KEY",
        transport=fake_transport(captured),
    )
    assert client("hi") == '{"ok": true}'
    request = captured[0]
    assert request["url"] == "https://api.example.com/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer sk-test"
    assert request["payload"]["model"] == "m1"
    assert request["payload"]["response_format"] == {"type": "json_object"}
    assert request["payload"]["messages"][1]["content"] == "hi"


def test_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    client = ChatClient(base_url="https://x/v1", model="m", api_key_env="MISSING_KEY")
    with pytest.raises(RuntimeError):
        client("hi")


def test_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_KEY", "k")
    calls = {"n": 0}

    def flaky(url: str, headers: dict, payload: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("timeout")
        return {"choices": [{"message": {"content": "ok"}}]}

    client = ChatClient(
        base_url="https://x/v1", model="m", api_key_env="TEST_KEY", transport=flaky, retries=1
    )
    assert client("hi") == "ok"
    assert calls["n"] == 2


def test_presets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    client = make_client("deepseek")
    assert client.base_url == "https://api.deepseek.com"
    assert client.model == "deepseek-chat"
    assert client.api_key == "k"
