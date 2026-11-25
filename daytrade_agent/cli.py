from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from daytrade_agent.calendar.trading_calendar import MORNING_START, premarket_cutoff, trading_status
from daytrade_agent.collectors import (
    corporate_disclosure,
    global_issue,
    political_theme,
    price_snapshot,
    theme_surge,
)
from daytrade_agent.collectors.base import CollectorResult
from daytrade_agent.collectors.mock import FIXTURE_VARIANTS, collect_mock
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
    MarketEvent,
    MarketMetric,
    PriceSnapshot,
    ReportContext,
    Source,
    VerificationResult,
    parse_datetime,
)
from daytrade_agent.normalizers.freshness import temporal_status
from daytrade_agent.normalizers.report_context import context_from_summary
from daytrade_agent.render.site_builder import apply_publication_gate, build_site
from daytrade_agent.scoring.candidate_score import score_candidates
from daytrade_agent.storage.public_safety import (
    PublicSafetyError,
    PublicSafetyIssue,
    is_isolatable_item_issues,
    public_artifact_issues,
    stored_safety_messages,
)
from daytrade_agent.storage.report_store import load_report, save_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = AppConfig.load(Path.cwd())

    if args.command == "run":
        if args.fixture and not args.dry_run:
            parser.error("--fixture requires --dry-run")
        return run_command(config, args.date, dry_run=args.dry_run,
                           fixture=args.fixture or "standard")
    if args.command == "verify":
        try:
            return verify_command(config, args.date)
        except Exception as exc:
            # Exit 1 is reserved for a successfully saved evidence-failure notice.
            print(f"Verification could not complete: {type(exc).__name__}", file=sys.stderr)
            return 2
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
    run_parser.add_argument("--fixture", choices=FIXTURE_VARIANTS, help="Select a mock scenario")

    verify_parser = subparsers.add_parser("verify", help="Verify an existing report")
    verify_parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD")

    subparsers.add_parser("build-site", help="Build the static GitHub Pages site")
    return parser


def run_command(
    config: AppConfig, report_date: str | None, *, dry_run: bool, fixture: str = "standard",
) -> int:
    now = datetime.now(ZoneInfo(config.timezone))
    selected_date = _report_date(report_date, config) if report_date else now.date().isoformat()
    if not dry_run and selected_date != now.date().isoformat():
        print("Live collection requires the current KST date; use --dry-run for fixtures.")
        return 2
    run_mode = "fixture" if dry_run else "live"
    if dry_run and (config.content_dir / selected_date).exists():
        try:
            stored = load_report(config.content_dir, selected_date)
        except (ValueError, OSError):
            stored = None
        if stored is None or stored["summary"].get("run_mode") != "fixture":
            print("Dry-run would overwrite a report; use a separate DAYTRADE_CONTENT_DIR.")
            return 2
    generated_at = _generated_at(selected_date, config, fixture=True) if dry_run else now
    market_status = trading_status(date.fromisoformat(selected_date))
    if market_status != "open":
        context = _market_closed_context(selected_date, generated_at, market_status, run_mode)
        markdown = market_closed_report_markdown(config, context)
        verification = verify_report(context, markdown)
        summary = build_summary(context, markdown, verification.status)
        save_report(config.content_dir, selected_date, markdown, summary, verification)
        print(f"saved market-closed report {selected_date} status={verification.status}")
        return 0
    cutoff = premarket_cutoff(generated_at.date())
    if not dry_run and generated_at >= cutoff:
        return _save_missed_notice(config, selected_date, generated_at)

    collected = (
        [collect_mock(config, selected_date, generated_at, variant=fixture)] if dry_run
        else _collect_all(config, selected_date, generated_at, dry_run=False)
    )
    context = _build_context(config, selected_date, generated_at, collected)
    context.market_context["run_mode"] = run_mode
    context.market_context["market_status"] = "open"

    if not dry_run and (now := datetime.now(ZoneInfo(config.timezone))) >= cutoff:
        return _save_missed_notice(config, selected_date, now)
    issues = public_artifact_issues("", build_summary(context, "", "pass"))
    if issues:
        return _block_artifact(config, context, issues)
    markdown = write_report_markdown(config, context, dry_run=dry_run)
    verification = verify_report(context, markdown)
    if verification.status == "fail":
        # A rejected LLM draft may only be replaced by independently verified facts.
        from daytrade_agent.llm.report_writer import verified_facts_markdown

        context.market_context["writer_fallback"] = True
        context.market_context["rejected_writer_model"] = context.market_context.get("writer_model")
        context.market_context["writer_provider"] = "template"
        context.market_context["writer_model"] = None
        markdown = verified_facts_markdown(config, context)
        verification = verify_report(context, markdown)
    if not dry_run and (now := datetime.now(ZoneInfo(config.timezone))) >= cutoff:
        return _save_missed_notice(config, selected_date, now)
    if verification.status == "fail":
        issues = public_artifact_issues(markdown, {})
        if issues:
            return _block_artifact(config, context, issues)
        _save_verification_failure(config, context, verification)
        print(f"saved report {selected_date} status=fail")
        return 0

    summary = build_summary(context, markdown, verification.status)
    try:
        save_report(config.content_dir, selected_date, markdown, summary, verification)
    except PublicSafetyError as exc:
        return _block_artifact(config, context, exc.issues)
    print(f"saved report {selected_date} status={verification.status}")
    return 0


def verify_command(config: AppConfig, report_date: str) -> int:
    report_date = _report_date(report_date, config)
    try:
        stored = load_report(config.content_dir, report_date)
    except FileNotFoundError:
        print(f"verification {report_date}: missing report artifact")
        return 2
    except ValueError:
        stored = {"verification": {}, "summary": {}, "markdown": ""}
    previous = stored["verification"]

    try:
        context = context_from_summary(stored["summary"])
        if context.report_date != report_date:
            raise ValueError("report date mismatch")
    except (ValueError, KeyError, TypeError):
        result = VerificationResult(
            status="fail",
            errors=[PublicSafetyIssue("summary", "invalid_schema").message()],
        )
        context = ReportContext(
            report_date=report_date, generated_at=_generated_at(report_date, config),
            data_status="insufficient", events=[], sources=[], price_snapshots=[], candidates=[],
        )
    else:
        if previous.get("status") in ("pass", "warning"):
            result = verify_report(context, stored["markdown"])
        else:
            errors = stored_safety_messages(previous.get("errors"))
            result = VerificationResult(
                status="fail",
                errors=errors or ["stored verification failed"],
            )
    issues = public_artifact_issues(stored["markdown"], stored["summary"], previous)
    if issues:
        result = VerificationResult(status="fail", errors=[issue.message() for issue in issues])

    if result.status == "fail":
        result = _save_verification_failure(config, context, result)
    else:
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
    stale_hours = float(config.risk_rules.get("stale_hours", 48))
    symbols = sorted(
        {
            symbol
            for result in event_results
            for event in result.events
            if event.data_status not in {"stale", "insufficient"}
            and temporal_status(event.published_at, generated_at, stale_hours) == "ok"
            and "\ufffd" not in event.title + event.summary
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
    raw_events = [event for result in results for event in result.events]
    sources = _dedupe_sources([source for result in results for source in result.sources])
    raw_snapshots = _dedupe_snapshots(
        [snapshot for result in results for snapshot in result.price_snapshots]
    )
    missing_data = [item for result in results for item in result.missing_data]
    source_by_id = {source.source_id: source for source in sources}
    stale_hours = float(config.risk_rules.get("stale_hours", 48))
    temporal_events = [
        event for event in raw_events
        if event.source_id in source_by_id
        and event.data_status not in {"stale", "insufficient"}
        and temporal_status(event.published_at, generated_at, stale_hours) == "ok"
        and "\ufffd" not in event.title + event.summary
    ]
    valid_events: list[MarketEvent] = []
    isolated_safety = 0
    for event in temporal_events:
        item_issues = public_artifact_issues(
            "",
            {
                "events": [event.model_dump(mode="json")],
                "sources": [source_by_id[event.source_id].model_dump(mode="json")],
            },
        )
        if is_isolatable_item_issues(item_issues):
            isolated_safety += 1
            continue
        valid_events.append(event)
    events = deduplicate_events(valid_events)
    used_source_ids = {event.source_id for event in events}
    sources = [source for source in sources if source.source_id in used_source_ids]
    snapshots = [snapshot for snapshot in raw_snapshots
                 if snapshot.last_price is not None
                 and snapshot.data_status not in {"stale", "insufficient"}
                 and temporal_status(snapshot.as_of, generated_at, 96) == "ok"]
    rejected = len(raw_events) - len(temporal_events)
    if rejected:
        missing_data.append(f"제외된 뉴스/공시: {rejected}건 (시각·출처·문자 인코딩 확인 필요)")
    if isolated_safety:
        missing_data.append(
            f"제외된 뉴스/공시: {isolated_safety}건 (공개 안전 기준 미충족 항목 격리)"
        )
    if len(snapshots) != len(raw_snapshots):
        missing_data.append("시각 또는 유효성이 확인되지 않은 가격 스냅샷 제외")
    market_context = _merge_market_context(results)
    market_context = {key: value for key, value in market_context.items()
                      if temporal_status(parse_datetime(value.get("as_of")),
                                         generated_at, 96) == "ok"}
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


def _report_date(value: str | None, config: AppConfig) -> str:
    if value:
        return date.fromisoformat(value).isoformat()
    return datetime.now(tz=ZoneInfo(config.timezone)).date().isoformat()


def _generated_at(report_date: str, config: AppConfig, *, fixture: bool = False) -> datetime:
    today = datetime.now(tz=ZoneInfo(config.timezone))
    if not fixture and report_date == today.date().isoformat():
        return today
    return datetime.combine(
        date.fromisoformat(report_date),
        MORNING_START,
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
        for key, value in result.market_context.items():
            if key not in {"kospi", "kosdaq", "usdkrw", "sp500", "nasdaq"}:
                continue
            try:
                merged[key] = MarketMetric.model_validate(value).model_dump(mode="json")
            except ValueError:
                continue
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
    if any(event.data_status != "ok" for event in events):
        return "partial"
    if any(snapshot.data_status != "ok" for snapshot in snapshots):
        return "partial"
    return "ok"


def _save_missed_notice(config: AppConfig, report_date: str, now: datetime) -> int:
    try:
        stored = load_report(config.content_dir, report_date)
    except (FileNotFoundError, ValueError):
        pass
    else:
        apply_publication_gate(stored, now)
        if stored["valid"] and stored["summary"].get("run_mode") == "live":
            print(f"missed-premarket retry; preserved verified archive {report_date}")
            return 0
    context = ReportContext(
        report_date=report_date, generated_at=now, data_status="insufficient",
        events=[], sources=[], price_snapshots=[], candidates=[],
        market_context={"market_status": "missed", "run_mode": "live"},
        missing_data=["장전 발행 마감 경과: 정규장 시작 이후 후보를 공개하지 않음"],
    )
    markdown = (
        f"# 장전 발행 지연 안내 - {report_date}\n\n"
        f"생성 시각: {now.isoformat()}\n\n"
        f"> {config.disclaimer}\n\n"
        "- 장전 발행 마감이 지나 관찰 후보를 공개하지 않습니다. data_key: report_metadata\n"
    )
    result = verify_report(context, markdown)
    save_report(config.content_dir, report_date, markdown,
                build_summary(context, markdown, result.status), result)
    print(f"saved missed-premarket notice {report_date}")
    return 0


def _save_verification_failure(
    config: AppConfig, context: ReportContext, result: VerificationResult,
) -> VerificationResult:
    context = ReportContext(
        report_date=context.report_date, generated_at=context.generated_at,
        data_status="insufficient", events=[], sources=[], price_snapshots=[], candidates=[],
        market_context={key: value for key, value in context.market_context.items()
                        if ((key == "run_mode" and value in ("fixture", "live")) or
                            (key == "market_status" and value in ("closed", "unknown", "missed")))},
    )
    markdown = failure_report_markdown(config, context, result.errors, result.warnings)
    save_report(config.content_dir, context.report_date, markdown,
                build_summary(context, markdown, result.status), result)
    return result


def _block_artifact(
    config: AppConfig, context: ReportContext, issues: list[PublicSafetyIssue],
) -> int:
    errors = [issue.message() for issue in issues]
    _save_verification_failure(config, context, VerificationResult(status="fail", errors=errors))
    for error in errors:
        print(f"ERROR: {error}")
    print(f"saved report {context.report_date} status=fail")
    return 0


def _market_closed_context(
    report_date: str,
    generated_at: datetime,
    market_status: str,
    run_mode: str,
) -> ReportContext:
    return ReportContext(
        report_date=report_date,
        generated_at=generated_at,
        data_status="insufficient",
        events=[],
        sources=[],
        price_snapshots=[],
        candidates=[],
        market_context={
            "market_status": market_status,
            "run_mode": run_mode,
            "calendar_provider": "XKRX + reviewed amendments",
        },
        missing_data=[f"market_closed: {report_date} is not an open KRX trading day"],
    )


if __name__ == "__main__":
    sys.exit(main())
