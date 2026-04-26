from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from daytrade_agent.calendar.trading_calendar import is_trading_day, load_holidays
from daytrade_agent.collectors import (
    corporate_disclosure,
    global_issue,
    political_theme,
    price_snapshot,
    theme_surge,
)
from daytrade_agent.collectors.base import CollectorResult
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import (
    build_summary,
    failure_report_markdown,
    market_closed_report_markdown,
    write_report_markdown,
)
from daytrade_agent.normalizers.deduplicate import deduplicate_events
from daytrade_agent.normalizers.event_schema import (
    Candidate,
    MarketEvent,
    PriceSnapshot,
    ReportContext,
    Source,
    parse_datetime,
)
from daytrade_agent.render.site_builder import build_site
from daytrade_agent.scoring.candidate_score import score_candidates
from daytrade_agent.storage.report_store import load_report, save_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.load(Path.cwd())

    if args.command == "run":
        return run_command(config, args.date, dry_run=args.dry_run)
    if args.command == "verify":
        return verify_command(config, args.date)
    if args.command == "build-site":
        return build_site_command(config)
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daytrade-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Generate a daily report")
    run_parser.add_argument("--date", default=None, help="Report date in YYYY-MM-DD")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mock collectors and no LLM API",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify an existing report")
    verify_parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD")

    subparsers.add_parser("build-site", help="Build the static GitHub Pages site")
    return parser


def run_command(config: AppConfig, report_date: str | None, *, dry_run: bool) -> int:
    selected_date = _report_date(report_date, config)
    generated_at = _generated_at(selected_date, config)
    if not _is_open_trading_day(config, selected_date):
        context = _market_closed_context(config, selected_date, generated_at)
        markdown = market_closed_report_markdown(config, context)
        verification = verify_report(context, markdown)
        summary = build_summary(context, markdown, verification.status)
        save_report(config.content_dir, selected_date, markdown, summary, verification)
        print(f"saved market-closed report {selected_date} status={verification.status}")
        return 0

    collected = _collect_all(config, selected_date, generated_at, dry_run=dry_run)
    context = _build_context(config, selected_date, generated_at, collected)

    markdown = write_report_markdown(config, context, dry_run=dry_run)
    verification = verify_report(context, markdown)
    if verification.status == "fail":
        markdown = failure_report_markdown(
            config,
            context,
            verification.errors,
            verification.warnings,
        )

    summary = build_summary(context, markdown, verification.status)
    save_report(config.content_dir, selected_date, markdown, summary, verification)
    print(f"saved report {selected_date} status={verification.status}")
    return 0


def verify_command(config: AppConfig, report_date: str) -> int:
    stored = load_report(config.content_dir, report_date)
    previous = stored["verification"]
    if previous.get("status") == "fail" and "데이터 검증 실패 리포트" in stored["markdown"]:
        print(f"verification {report_date} status=fail")
        for error in previous.get("errors", []):
            print(f"ERROR: {error}")
        return 1

    context = _context_from_summary(stored["summary"])
    result = verify_report(context, stored["markdown"])
    summary = dict(stored["summary"])
    summary["verification_status"] = result.status
    save_report(config.content_dir, report_date, stored["markdown"], summary, result)
    print(f"verification {report_date} status={result.status}")
    for error in result.errors:
        print(f"ERROR: {error}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    return 1 if result.status == "fail" else 0


def build_site_command(config: AppConfig) -> int:
    created = build_site(config)
    print(f"built site with {len(created)} files in {config.dist_dir}")
    return 0


def _collect_all(
    config: AppConfig,
    report_date: str,
    generated_at: datetime,
    *,
    dry_run: bool,
) -> list[CollectorResult]:
    event_results = [
        political_theme.collect(config, report_date, generated_at, dry_run),
        corporate_disclosure.collect(config, report_date, generated_at, dry_run),
        global_issue.collect(config, report_date, generated_at, dry_run),
        theme_surge.collect(config, report_date, generated_at, dry_run),
    ]
    symbols = sorted(
        {
            symbol
            for result in event_results
            for event in result.events
            for symbol in event.candidate_symbols
        }
    )
    price_result = price_snapshot.collect(config, report_date, generated_at, dry_run, symbols)
    return [*event_results, price_result]


def _build_context(
    config: AppConfig,
    report_date: str,
    generated_at: datetime,
    results: list[CollectorResult],
) -> ReportContext:
    events = deduplicate_events([event for result in results for event in result.events])
    sources = _dedupe_sources([source for result in results for source in result.sources])
    snapshots = _dedupe_snapshots(
        [snapshot for result in results for snapshot in result.price_snapshots]
    )
    missing_data = [item for result in results for item in result.missing_data]
    market_context = _merge_market_context(results)
    candidates = score_candidates(config, events, snapshots, generated_at)
    data_status = _data_status(events, snapshots, missing_data)
    return ReportContext(
        report_date=report_date,
        generated_at=generated_at,
        data_status=data_status,
        events=events,
        sources=sources,
        price_snapshots=snapshots,
        candidates=candidates,
        market_context=market_context,
        missing_data=missing_data,
    )


def _context_from_summary(summary: dict[str, object]) -> ReportContext:
    snapshots = [
        PriceSnapshot.model_validate(item)
        for item in summary.get("price_snapshots", [])
        if isinstance(item, dict)
    ]
    snapshots_by_key = {snapshot.data_key: snapshot for snapshot in snapshots}
    candidates: list[Candidate] = []
    for item in summary.get("candidates", []):
        if not isinstance(item, dict):
            continue
        data_key = item.get("data_key")
        candidates.append(
            Candidate(
                symbol=str(item["symbol"]),
                name=str(item["name"]),
                market=str(item.get("market", "KRX")),
                categories=item.get("categories", []),
                score=float(item.get("score", 0)),
                main_reason=str(item.get("main_reason", "데이터 부족")),
                source_ids=item.get("source_ids", []),
                price_snapshot=snapshots_by_key.get(data_key) if data_key else None,
                risk_flags=item.get("risk_flags", []),
                observation_condition=str(item.get("observation_condition", "데이터 부족")),
                invalidation_condition=str(item.get("invalidation_condition", "데이터 부족")),
            )
        )
    return ReportContext(
        report_date=str(summary["report_date"]),
        generated_at=parse_datetime(str(summary["generated_at"]))
        or datetime.now(tz=ZoneInfo("Asia/Seoul")),
        data_status=summary.get("data_status", "insufficient"),
        events=[
            MarketEvent.model_validate(item)
            for item in summary.get("events", [])
            if isinstance(item, dict)
        ],
        sources=[
            Source.model_validate(item)
            for item in summary.get("sources", [])
            if isinstance(item, dict)
        ],
        price_snapshots=snapshots,
        candidates=candidates,
        market_context=summary.get("market_context", {})
        if isinstance(summary.get("market_context"), dict)
        else {},
        missing_data=[
            str(item) for item in summary.get("missing_data", []) if isinstance(item, str)
        ],
    )


def _report_date(value: str | None, config: AppConfig) -> str:
    if value:
        date.fromisoformat(value)
        return value
    return datetime.now(tz=ZoneInfo(config.timezone)).date().isoformat()


def _generated_at(report_date: str, config: AppConfig) -> datetime:
    today = datetime.now(tz=ZoneInfo(config.timezone))
    if report_date == today.date().isoformat():
        return today
    return datetime.combine(
        date.fromisoformat(report_date),
        time(hour=8, minute=45),
        ZoneInfo(config.timezone),
    )


def _dedupe_sources(sources: list[Source]) -> list[Source]:
    by_id: dict[str, Source] = {}
    for source in sources:
        by_id[source.source_id] = source
    return list(by_id.values())


def _dedupe_snapshots(snapshots: list[PriceSnapshot]) -> list[PriceSnapshot]:
    by_symbol: dict[str, PriceSnapshot] = {}
    for snapshot in snapshots:
        by_symbol[snapshot.symbol] = snapshot
    return list(by_symbol.values())


def _merge_market_context(results: list[CollectorResult]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for result in results:
        merged.update(result.market_context)
    return merged


def _data_status(
    events: list[MarketEvent],
    snapshots: list[PriceSnapshot],
    missing_data: list[str],
) -> str:
    if not events:
        return "insufficient"
    if missing_data or not snapshots:
        return "partial"
    if any(event.data_status in {"insufficient", "stale"} for event in events):
        return "partial"
    return "ok"


def _is_open_trading_day(config: AppConfig, report_date: str) -> bool:
    value = date.fromisoformat(report_date)
    holidays_path = config.root / "config" / "holidays_kr.yml"
    if not holidays_path.exists():
        holidays_path = config.root / "config" / "holidays_kr.example.yml"
    return is_trading_day(value, load_holidays(holidays_path))


def _market_closed_context(
    config: AppConfig,
    report_date: str,
    generated_at: datetime,
) -> ReportContext:
    _ = config
    return ReportContext(
        report_date=report_date,
        generated_at=generated_at,
        data_status="insufficient",
        events=[],
        sources=[],
        price_snapshots=[],
        candidates=[],
        market_context={"market_status": "closed"},
        missing_data=[f"market_closed: {report_date} is not an open KRX trading day"],
    )


if __name__ == "__main__":
    sys.exit(main())
