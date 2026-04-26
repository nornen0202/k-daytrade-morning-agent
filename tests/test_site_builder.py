from datetime import datetime
from zoneinfo import ZoneInfo

from daytrade_agent.collectors.mock import collect_mock
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import build_summary, write_report_markdown
from daytrade_agent.normalizers.event_schema import ReportContext
from daytrade_agent.render.site_builder import build_site
from daytrade_agent.scoring.candidate_score import score_candidates
from daytrade_agent.storage.report_store import save_report


def test_site_builder_creates_expected_pages(tmp_path):
    config = AppConfig.load()
    config = AppConfig(
        **{
            **config.__dict__,
            "content_dir": tmp_path / "content" / "reports",
            "dist_dir": tmp_path / "dist",
        }
    )
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)
    context = ReportContext(
        report_date="2026-04-27",
        generated_at=generated_at,
        data_status="ok",
        events=result.events,
        sources=result.sources,
        price_snapshots=result.price_snapshots,
        candidates=score_candidates(config, result.events, result.price_snapshots, generated_at),
        market_context=result.market_context,
    )
    markdown = write_report_markdown(config, context, dry_run=True)
    verification = verify_report(context, markdown)
    save_report(
        config.content_dir,
        "2026-04-27",
        markdown,
        build_summary(context, markdown, verification.status),
        verification,
    )

    build_site(config)

    assert (config.dist_dir / "index.html").exists()
    assert (config.dist_dir / "reports" / "index.html").exists()
    assert (config.dist_dir / "reports" / "2026-04-27" / "index.html").exists()
    assert (config.dist_dir / "assets" / "style.css").exists()
