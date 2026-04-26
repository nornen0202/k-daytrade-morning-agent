from __future__ import annotations

from datetime import datetime

from daytrade_agent.collectors.base import CollectorResult
from daytrade_agent.collectors.mock import collect_category_mock
from daytrade_agent.collectors.news_provider import collect_news_category
from daytrade_agent.config import AppConfig


def collect(
    config: AppConfig,
    report_date: str,
    collected_at: datetime,
    dry_run: bool,
) -> CollectorResult:
    _ = report_date
    if dry_run:
        return collect_category_mock(config, "global_issue", collected_at)
    return collect_news_category(config, "global_issue", collected_at)
