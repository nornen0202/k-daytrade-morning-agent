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


def test_independent_events_handles_none_published_at_ties():
    from daytrade_agent.normalizers.deduplicate import independent_events

    dated = MarketEvent(
        event_id="evt_dated",
        category="political_theme",
        title="개별 정책 브리핑 A",
        summary="요약 A",
        published_at=parse_datetime("2026-04-27T08:30:00+09:00"),
        source_id="src_a",
        source_name="Source A",
        source_quality=0.8,
        confidence=0.7,
    )
    undated = MarketEvent(
        event_id="evt_undated",
        category="corporate_disclosure",
        title="공시 접수 B",
        summary="요약 B",
        published_at=None,
        source_id="src_b",
        source_name="OpenDART",
        source_quality=0.8,
        confidence=0.7,
    )
    ordered = independent_events([undated, dated])
    assert [item.event_id for item in ordered] == ["evt_dated", "evt_undated"]


def test_status_js_schedules_retry_when_client_clock_lags_server():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = (Path(__file__).resolve().parents[1] / "site_templates/assets/status.js").read_text(
        encoding="utf-8",
    )
    harness = f"""
const timers = [];
let now = Date.parse("2026-04-27T08:44:58+09:00");
Date.now = () => now;
globalThis.setTimeout = (fn, ms) => {{ timers.push({{ fn, ms }}); return timers.length; }};
globalThis.clearTimeout = () => {{}};
const brief = {{
  hidden: false,
  dataset: {{ expires: "2026-04-27T09:00:00+09:00", reportDate: "2026-04-27" }},
}};
const notice = {{ dataset: {{ asOf: "2026-04-27T08:45:00+09:00" }}, textContent: "" }};
globalThis.document = {{
  getElementById: (id) => (id === "current-brief" ? brief : notice),
  addEventListener: () => {{}},
}};
globalThis.window = {{ addEventListener: () => {{}} }};
{script}
if (!brief.hidden || timers.length !== 1) process.exit(1);
now = Date.parse("2026-04-27T08:45:01+09:00");
timers[0].fn();
if (brief.hidden) process.exit(2);
"""
    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

