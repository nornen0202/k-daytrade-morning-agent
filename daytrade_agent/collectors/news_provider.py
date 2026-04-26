from __future__ import annotations

import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests

from daytrade_agent.collectors.base import CollectorResult, insufficient_result
from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import MarketEvent, Source, parse_datetime, stable_id

_NAVER_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"


def collect_news_category(
    config: AppConfig,
    category: str,
    collected_at: datetime,
) -> CollectorResult:
    rss_urls = _rss_urls(config)
    if rss_urls:
        return _collect_rss(category, rss_urls, collected_at)

    if config.env("NAVER_CLIENT_ID") and config.env("NAVER_CLIENT_SECRET"):
        return _collect_naver(category, _queries(config, category), collected_at, config)

    if config.env("NEWS_API_KEY"):
        return _collect_newsapi(category, _queries(config, category), collected_at, config)

    return insufficient_result(
        category,
        "NEWS_RSS_URLS, NAVER_CLIENT_ID/NAVER_CLIENT_SECRET, or NEWS_API_KEY is not configured",
    )


def _collect_rss(category: str, rss_urls: list[str], collected_at: datetime) -> CollectorResult:
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for url in rss_urls:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        for item in root.findall(".//item")[:10]:
            title = _strip_html(item.findtext("title") or "데이터 부족")
            link = item.findtext("link") or url
            summary = _strip_html(item.findtext("description") or "데이터 부족")
            published = parse_datetime(item.findtext("pubDate"))
            event, source = _event_and_source(
                category=category,
                provider="rss",
                title=title,
                summary=summary,
                url=link,
                published=published,
                collected_at=collected_at,
                source_quality=0.55,
            )
            events.append(event)
            sources.append(source)
    return CollectorResult(events=events, sources=sources)


def _collect_naver(
    category: str,
    queries: list[str],
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    headers = {
        "X-Naver-Client-Id": config.env("NAVER_CLIENT_ID") or "",
        "X-Naver-Client-Secret": config.env("NAVER_CLIENT_SECRET") or "",
    }
    endpoint = str(config.data_sources.get("news", {}).get("naver_endpoint") or _NAVER_ENDPOINT)
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for query in queries:
        response = requests.get(
            endpoint,
            headers=headers,
            params={"query": query, "display": 10, "sort": "date"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            title = _strip_html(str(item.get("title") or "데이터 부족"))
            summary = _strip_html(str(item.get("description") or "데이터 부족"))
            published = _parse_pubdate(item.get("pubDate"))
            event, source = _event_and_source(
                category=category,
                provider="Naver News",
                title=title,
                summary=summary,
                url=str(item.get("originallink") or item.get("link") or ""),
                published=published,
                collected_at=collected_at,
                source_quality=0.65,
            )
            events.append(event)
            sources.append(source)
    return _dedupe_result(events, sources)


def _collect_newsapi(
    category: str,
    queries: list[str],
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    endpoint = str(config.data_sources.get("news", {}).get("newsapi_endpoint") or _NEWSAPI_ENDPOINT)
    headers = {"X-Api-Key": config.env("NEWS_API_KEY") or ""}
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for query in queries:
        response = requests.get(
            endpoint,
            headers=headers,
            params={"q": query, "pageSize": 10, "sortBy": "publishedAt"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("articles", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            event, source_ref = _event_and_source(
                category=category,
                provider=str(source.get("name") or "NewsAPI"),
                title=_strip_html(str(item.get("title") or "데이터 부족")),
                summary=_strip_html(str(item.get("description") or "데이터 부족")),
                url=str(item.get("url") or ""),
                published=parse_datetime(item.get("publishedAt")),
                collected_at=collected_at,
                source_quality=0.55,
            )
            events.append(event)
            sources.append(source_ref)
    return _dedupe_result(events, sources)


def _event_and_source(
    *,
    category: str,
    provider: str,
    title: str,
    summary: str,
    url: str,
    published: datetime | None,
    collected_at: datetime,
    source_quality: float,
) -> tuple[MarketEvent, Source]:
    source_id = stable_id("src", provider, url, title)
    source_url = url if url.startswith(("http://", "https://")) else None
    event = MarketEvent(
        event_id=stable_id("evt", category, source_id, title),
        category=category,
        title=title,
        summary=summary,
        published_at=published,
        source_id=source_id,
        source_url=source_url,
        source_name=provider,
        source_quality=source_quality,
        affected_sectors=_affected_sectors(title, summary),
        candidate_symbols=[],
        confidence=0.5,
        data_status="partial",
    )
    source = Source(
        source_id=source_id,
        source_name=provider,
        source_url=source_url,
        source_type=category,
        published_at=published,
        collected_at=collected_at,
        source_quality=source_quality,
    )
    return event, source


def _dedupe_result(events: list[MarketEvent], sources: list[Source]) -> CollectorResult:
    by_event_id = {event.event_id: event for event in events}
    by_source_id = {source.source_id: source for source in sources}
    return CollectorResult(events=list(by_event_id.values()), sources=list(by_source_id.values()))


def _queries(config: AppConfig, category: str) -> list[str]:
    news_config = config.data_sources.get("news", {})
    query_map = news_config.get("query_map", {}) if isinstance(news_config, dict) else {}
    raw_queries = query_map.get(category, []) if isinstance(query_map, dict) else []
    if isinstance(raw_queries, list):
        queries = [str(query).strip() for query in raw_queries if str(query).strip()]
    else:
        queries = []
    fallback = {
        "political_theme": ["한국 정책 주식", "정부 산업 정책 증시"],
        "global_issue": ["미국 증시 금리 환율 반도체", "중국 경기 원자재 한국 증시"],
        "theme_surge": ["시간외 급등 테마 주식", "장전 테마 거래대금"],
    }
    return queries or fallback.get(category, ["한국 증시"])


def _rss_urls(config: AppConfig) -> list[str]:
    value = config.env("NEWS_RSS_URLS")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_pubdate(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return parse_datetime(parsedate_to_datetime(str(value)))
    except (TypeError, ValueError, IndexError):
        return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(text or "")).strip()


def _affected_sectors(title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".lower()
    rules = {
        "semiconductor": ["반도체", "chip", "semiconductor", "hbm"],
        "battery": ["배터리", "battery", "2차전지", "전기차"],
        "robotics": ["로봇", "robot"],
        "defense": ["방산", "defense", "국방"],
        "bio": ["바이오", "제약", "bio"],
        "ai": ["ai", "인공지능"],
    }
    return [
        sector
        for sector, keywords in rules.items()
        if any(keyword in text for keyword in keywords)
    ]
