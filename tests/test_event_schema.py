from datetime import datetime

import pytest
from pydantic import ValidationError

from daytrade_agent.normalizers.event_schema import MarketEvent, parse_datetime


def test_market_event_requires_known_category():
    with pytest.raises(ValidationError):
        MarketEvent(
            event_id="evt",
            category="unknown",
            title="title",
            summary="summary",
            source_id="src",
            source_name="source",
        )


def test_parse_datetime_applies_timezone():
    parsed = parse_datetime("2026-04-27T08:45:00+09:00")
    assert isinstance(parsed, datetime)
    assert parsed.isoformat() == "2026-04-27T08:45:00+09:00"

