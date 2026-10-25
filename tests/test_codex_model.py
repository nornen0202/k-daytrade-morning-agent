import json

from daytrade_agent.config import AppConfig
from daytrade_agent.llm import report_writer


def test_codex_default_comes_from_project_config(monkeypatch):
    monkeypatch.delenv("CODEX_REPORT_MODEL", raising=False)
    assert AppConfig.load().codex_model == "gpt-6.1-sol"
    monkeypatch.setenv("CODEX_REPORT_MODEL", "")
    assert AppConfig.load().codex_model == "gpt-6.1-sol"


def test_codex_model_override_is_explicit(monkeypatch):
    monkeypatch.setenv("CODEX_REPORT_MODEL", "gpt-6-astra")
    assert AppConfig.load().codex_model == "gpt-6-astra"


def test_writer_passes_selected_model_and_preserves_limits(monkeypatch):
    calls = []

    class Session:
        def __init__(self, **kwargs):
            assert kwargs["request_timeout"] == 180

        def invoke(self, **kwargs):
            calls.append(kwargs)
            return type("Result", (), {"final_text": json.dumps({"answer": "verified text"})})()

        def close(self):
            pass

    monkeypatch.delenv("CODEX_REPORT_MODEL", raising=False)
    monkeypatch.delenv("CODEX_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("CODEX_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(report_writer, "CodexAppServerSession", Session)
    # Only this mocked session bypasses the default no-network guard.
    assert report_writer._try_codex.__wrapped__("facts", AppConfig.load()) == "verified text"
    assert calls[0]["model"] == "gpt-6.1-sol"
    assert calls[0]["reasoning_effort"] == "medium"


def test_codex_child_does_not_receive_paid_api_or_collector_keys(monkeypatch):
    from daytrade_agent.llm.codex_app_server import codex_process_environment

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "fixture-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")
    monkeypatch.setenv("CODEX_REPORT_MODEL", "gpt-6.1-sol")
    environment = codex_process_environment()
    assert "OPENAI_API_KEY" not in environment
    assert "NAVER_CLIENT_SECRET" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert environment["CODEX_REPORT_MODEL"] == "gpt-6.1-sol"
