from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

import requests

from daytrade_agent.collectors.base import CollectorResult, insufficient_result
from daytrade_agent.collectors.mock import collect_category_mock
from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import MarketEvent, Source, parse_datetime, stable_id


def collect(
    config: AppConfig,
    report_date: str,
    collected_at: datetime,
    dry_run: bool,
) -> CollectorResult:
    if dry_run:
        return collect_category_mock(config, "political_theme", collected_at)
    rss_urls = _rss_urls(config)
    if not rss_urls:
        return insufficient_result("political_theme", "NEWS_RSS_URLS is not configured")
    return _collect_rss("political_theme", rss_urls, collected_at)


def _collect_rss(category: str, rss_urls: list[str], collected_at: datetime) -> CollectorResult:
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for url in rss_urls:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title") or "데이터 부족"
            link = item.findtext("link") or url
            published = parse_datetime(item.findtext("pubDate"))
            source_id = stable_id("src", category, link, title)
            event = MarketEvent(
                event_id=stable_id("evt", category, source_id, title),
                category=category,
                title=title,
                summary=item.findtext("description") or "데이터 부족",
                published_at=published,
                source_id=source_id,
                source_url=link,
                source_name="rss",
                source_quality=0.55,
                affected_sectors=[],
                candidate_symbols=[],
                confidence=0.45,
                data_status="partial",
            )
            events.append(event)
            sources.append(
                Source(
                    source_id=source_id,
                    source_name="rss",
                    source_url=link,
                    source_type=category,
                    published_at=published,
                    collected_at=collected_at,
                    source_quality=0.55,
                )
            )
    return CollectorResult(events=events, sources=sources)


def _rss_urls(config: AppConfig) -> list[str]:
    value = config.env("NEWS_RSS_URLS")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
