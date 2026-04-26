from datetime import datetime
from types import SimpleNamespace
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
    config.data_sources["news"]["provider_priority"] = ["naver"]

    def fake_get(url, *, headers=None, params=None, timeout=None):
        assert url == "https://openapi.naver.com/v1/search/news.json"
        assert headers["X-Naver-Client-Id"] == "client-id"
        assert params["sort"] == "date"
        assert timeout == 15
        return _FakeResponse(
            {
                "items": [
                    {
                        "title": "<b>반도체</b> 123456 정책 뉴스",
                        "description": "정부 산업 정책 관련 보도와 작전주 및 계좌 표현",
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
    assert result.events[0].title == "반도체 종목코드 확인 필요 정책 뉴스"
    assert "근거 부족 테마" in result.events[0].summary
    assert "금융계정 관련 표현" in result.events[0].summary
    assert result.events[0].affected_sectors == ["semiconductor"]
    assert result.sources[0].source_url is not None


def test_news_provider_collects_newsapi_and_alpha_vantage(monkeypatch):
    config = AppConfig.load()
    collected_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    config.data_sources["news"]["provider_priority"] = ["newsapi", "alpha_vantage"]
    monkeypatch.setenv("NEWS_API_KEY", "news-key")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "alpha-key")

    def fake_get(url, *, headers=None, params=None, timeout=None):
        if "newsapi.org" in url:
            assert headers["X-Api-Key"] == "news-key"
            return _FakeResponse(
                {
                    "articles": [
                        {
                            "title": "배터리 정책 뉴스",
                            "description": "전기차 공급망 관련 보도",
                            "url": "https://example.com/newsapi",
                            "publishedAt": "2026-04-27T08:00:00+09:00",
                            "source": {"name": "NewsAPI Source"},
                        }
                    ]
                }
            )
        assert params["apikey"] == "alpha-key"
        return _FakeResponse(
            {
                "feed": [
                    {
                        "title": "AI market update",
                        "summary": "Semiconductor and AI market context",
                        "url": "https://example.com/alpha",
                        "time_published": "20260427T075500",
                        "source": "Alpha Vantage",
                    }
                ]
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    result = collect_news_category(config, "global_issue", collected_at)

    assert {event.source_name for event in result.events} == {"NewsAPI Source", "Alpha Vantage"}
    assert len(result.sources) == 2


def test_news_provider_uses_yfinance(monkeypatch):
    config = AppConfig.load()
    collected_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    config.data_sources["news"]["provider_priority"] = ["yfinance"]
    config.data_sources["news"]["yfinance_tickers"] = {"theme_surge": ["005930.KS"]}

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def get_news(self, count=8):
            assert count == 8
            return [
                {
                    "title": "Samsung AI chip update",
                    "summary": "AI semiconductor article",
                    "publisher": "Yahoo Finance",
                    "link": "https://example.com/yf",
                    "providerPublishTime": 1777247100,
                }
            ]

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        SimpleNamespace(Ticker=FakeTicker),
    )

    result = collect_news_category(config, "theme_surge", collected_at)

    assert result.events[0].source_name == "Yahoo Finance"
    assert result.events[0].candidate_symbols == ["005930"]
