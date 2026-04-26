from __future__ import annotations

from datetime import datetime

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
        return collect_category_mock(config, "corporate_disclosure", collected_at)
    api_key = config.env("OPENDART_API_KEY")
    if not api_key:
        return insufficient_result("corporate_disclosure", "OPENDART_API_KEY is not configured")

    yyyymmdd = report_date.replace("-", "")
    url = str(config.data_sources["opendart"]["list_url"])
    response = requests.get(
        url,
        params={
            "crtfc_key": api_key,
            "bgn_de": yyyymmdd,
            "end_de": yyyymmdd,
            "page_count": 100,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("list", []) if isinstance(payload, dict) else []

    events: list[MarketEvent] = []
    sources: list[Source] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stock_code = str(row.get("stock_code") or "").strip()
        corp_name = str(row.get("corp_name") or stock_code or "UNKNOWN")
        title = str(row.get("report_nm") or "공시")
        receipt_no = str(row.get("rcept_no") or "")
        source_url = (
            f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}" if receipt_no else None
        )
        source_id = stable_id("src", "opendart", receipt_no, title)
        published = parse_datetime(_receipt_time(row.get("rcept_dt"), row.get("rcept_time")))
        event = MarketEvent(
            event_id=stable_id("evt", "corporate_disclosure", source_id, title),
            category="corporate_disclosure",
            title=title,
            summary=f"{corp_name} 공시 접수. 원문 확인 필요.",
            published_at=published,
            source_id=source_id,
            source_url=source_url,
            source_name="OpenDART",
            source_quality=0.8,
            affected_sectors=[],
            candidate_symbols=[stock_code] if stock_code else [],
            confidence=0.7 if stock_code else 0.4,
            data_status="ok",
        )
        events.append(event)
        sources.append(
            Source(
                source_id=source_id,
                source_name="OpenDART",
                source_url=source_url,
                source_type="disclosure",
                published_at=published,
                collected_at=collected_at,
                source_quality=0.8,
            )
        )
    return CollectorResult(events=events, sources=sources)


def _receipt_time(date_value: object, time_value: object) -> str | None:
    date_text = str(date_value or "").strip()
    if len(date_text) != 8:
        return None
    time_text = str(time_value or "084500").strip().zfill(6)[:6]
    return (
        f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"
        f"T{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}+09:00"
    )
