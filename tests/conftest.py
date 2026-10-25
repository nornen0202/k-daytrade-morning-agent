import socket
from functools import wraps

import pytest
import requests

from daytrade_agent.llm import report_writer


@pytest.fixture(autouse=True)
def offline_tests(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for name in ("OPENAI_API_KEY", "OPENDART_API_KEY", "NEWS_API_KEY", "NAVER_CLIENT_ID",
                 "NAVER_CLIENT_SECRET", "ALPHA_VANTAGE_API_KEY", "QUOTE_PROVIDER_URL",
                 "QUOTE_PROVIDER_API_KEY", "KIS_APP_KEY", "KIS_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)

    def reject(*args, **kwargs):
        raise AssertionError("Unit tests must not access external APIs")

    monkeypatch.setattr(requests.Session, "request", reject)
    monkeypatch.setattr(report_writer, "_try_openai", reject)
    @wraps(report_writer._try_codex)
    def reject_codex(*args, **kwargs):
        return reject(*args, **kwargs)

    monkeypatch.setattr(report_writer, "_try_codex", reject_codex)
    monkeypatch.setattr(socket, "create_connection", reject)
