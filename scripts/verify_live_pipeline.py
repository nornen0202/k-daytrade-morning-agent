"""Manually verify live news evidence; never replaces a daily report."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from daytrade_agent.cli import _build_context, _collect_all
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import build_summary, verified_facts_markdown
from daytrade_agent.render.site_builder import build_site
from daytrade_agent.storage.report_store import save_report


def main() -> int:
    config = AppConfig.load()
    stamp = datetime.now(ZoneInfo("Asia/Seoul"))
    report_date = stamp.date().isoformat()
    config.data_sources["news"]["provider_priority"] = ["naver"]
    context = _build_context(
        config, report_date, stamp,
        _collect_all(config, report_date, stamp, dry_run=False),
    )
    context.market_context["run_mode"] = "live_audit"
    markdown = verified_facts_markdown(config, context)
    result = verify_report(context, markdown)
    audit_root = config.private_artifacts_dir / "live-pipeline-check"
    config = replace(config, content_dir=audit_root / "content", dist_dir=audit_root / "dist")
    save_report(
        config.content_dir, report_date, markdown,
        build_summary(context, markdown, result.status), result,
    )
    build_site(config)
    print(f"Live events: {len(context.events)}; status: {result.status}")
    for error in result.errors:
        print(error)
    print(f"Private evidence: {audit_root}")
    return 1 if result.status == "fail" or not context.events else 0


if __name__ == "__main__":
    raise SystemExit(main())
