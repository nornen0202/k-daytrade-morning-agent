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


def test_codex_auth_cleanup_does_not_delete_in_place_and_cleans_after_popen_failure(
    monkeypatch, tmp_path
):
    from daytrade_agent.llm import codex_app_server
    from daytrade_agent.llm.codex_app_server import (
        CodexAppServerBinaryError,
        CodexAppServerSession,
    )

    # Case 1: source CODEX_HOME equals session .codex-home -> must NEVER delete auth.json.
    workspace = tmp_path / "ws_inplace"
    session_home = workspace / ".codex-home"
    session_home.mkdir(parents=True)
    auth_file = session_home / "auth.json"
    auth_file.write_text('{"token": "keep"}', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(session_home))
    session = CodexAppServerSession(
        codex_binary="codex",
        request_timeout=10.0,
        workspace_dir=str(workspace),
        cleanup_threads=True,
    )
    session.close()
    assert auth_file.exists()

    # Case 2: seeded copy removed even if Popen fails during start().
    source_home = tmp_path / "src_home"
    source_home.mkdir()
    (source_home / "auth.json").write_text('{"token": "copy"}', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    ws2 = tmp_path / "ws_copy"
    monkeypatch.setattr(codex_app_server, "resolve_codex_binary", lambda *_: "fake-codex")

    def fail_popen(*args, **kwargs):
        raise OSError("cannot launch")

    monkeypatch.setattr(codex_app_server.subprocess, "Popen", fail_popen)
    session2 = CodexAppServerSession(
        codex_binary="fake-codex",
        request_timeout=10.0,
        workspace_dir=str(ws2),
        cleanup_threads=True,
    )
    import pytest

    with pytest.raises(CodexAppServerBinaryError):
        session2.start()
    assert not (ws2 / ".codex-home" / "auth.json").exists()
    assert (source_home / "auth.json").exists()


def test_openai_writer_records_model_and_fallback_metadata(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from daytrade_agent.normalizers.event_schema import ReportContext

    ctx = ReportContext(
        report_date="2026-04-27",
        generated_at=datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul")),
        data_status="partial",
        events=[],
        sources=[],
        price_snapshots=[],
        candidates=[],
    )
    monkeypatch.setenv("REPORT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report_writer.write_report_markdown(AppConfig.load(), ctx, dry_run=False)
    assert ctx.market_context["writer_provider"] == "template"
    assert ctx.market_context["writer_fallback"] is True

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_REPORT_MODEL", "gpt-5.5")
    monkeypatch.setattr(report_writer, "_try_openai", lambda *args, **kwargs: "# ok")
    ctx2 = ctx.model_copy(deep=True)
    ctx2.market_context = {}
    assert report_writer.write_report_markdown(AppConfig.load(), ctx2, dry_run=False) == "# ok"
    assert ctx2.market_context["writer_provider"] == "openai"
    assert ctx2.market_context["writer_model"] == "gpt-5.5"
