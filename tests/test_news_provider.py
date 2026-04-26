from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from daytrade_agent.collectors.news_provider import collect_news_category
from daytrade_agent.config import AppConfig


class _FakeResponse:
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_news_provider_uses_naver_when_configured(monkeypatch):
    config = AppConfig.load()
    collected_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))

    monkeypatch.delenv("NEWS_RSS_URLS", raising=False)
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    monkeypatch.setenv("NAVER_CLIENT_ID", "client-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "client-secret")

    def fake_get(url, *, headers=None, params=None, timeout=None):
        assert url == "https://openapi.naver.com/v1/search/news.json"
        assert headers["X-Naver-Client-Id"] == "client-id"
        assert params["sort"] == "date"
        assert timeout == 15
        return _FakeResponse(
            {
                "items": [
                    {
                        "title": "<b>반도체</b> 정책 뉴스",
                        "description": "정부 산업 정책 관련 보도",
                        "originallink": "https://example.com/news/1",
                        "pubDate": "Mon, 27 Apr 2026 08:10:00 +0900",
                    }
                ]
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    result = collect_news_category(config, "political_theme", collected_at)

    assert result.events
    assert result.events[0].source_name == "Naver News"
    assert result.events[0].title == "반도체 정책 뉴스"
    assert result.events[0].affected_sectors == ["semiconductor"]
    assert result.sources[0].source_url is not None
