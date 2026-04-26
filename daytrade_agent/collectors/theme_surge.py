from __future__ import annotations

from datetime import datetime

from daytrade_agent.collectors.base import CollectorResult, insufficient_result
from daytrade_agent.collectors.mock import collect_category_mock
from daytrade_agent.collectors.political_theme import _collect_rss, _rss_urls
from daytrade_agent.config import AppConfig


def collect(
    config: AppConfig,
    report_date: str,
    collected_at: datetime,
    dry_run: bool,
) -> CollectorResult:
    _ = report_date
    if dry_run:
        return collect_category_mock(config, "theme_surge", collected_at)
    rss_urls = _rss_urls(config)
    if not rss_urls:
        return insufficient_result("theme_surge", "NEWS_RSS_URLS is not configured")
    return _collect_rss("theme_surge", rss_urls, collected_at)
