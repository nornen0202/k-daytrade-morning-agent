from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from daytrade_agent.calendar.trading_calendar import premarket_cutoff, trading_status
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import build_summary
from daytrade_agent.normalizers.report_context import context_from_summary
from daytrade_agent.render.markdown import markdown_to_html
from daytrade_agent.storage.public_safety import public_artifact_issues, stored_safety_messages
from daytrade_agent.storage.report_store import discover_reports


def build_site(config: AppConfig, *, now: datetime | None = None) -> list[Path]:
    kst = ZoneInfo("Asia/Seoul")
    now = (now or datetime.now(kst)).astimezone(kst)
    reports = discover_reports(config.content_dir)
    for report in reports:
        apply_publication_gate(report, now)
    dist = config.dist_dir
    resolved = dist.resolve()
    protected = (config.content_dir.resolve(), config.private_artifacts_dir.resolve())
    if config.root.resolve().is_relative_to(resolved) or any(
        path.is_relative_to(resolved) or resolved.is_relative_to(path) for path in protected
    ):
        raise ValueError("site output overlaps source or private data")
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "reports").mkdir(parents=True, exist_ok=True)
    (dist / "assets").mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(config.site_templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["kst_display"] = _kst_display

    created: list[Path] = []
    latest = reports[0] if reports else None
    valid = next((report for report in reports if report["valid"]), None)
    current = next((report for report in reports if report["current"]), None)
    state = {
        "schema_version": 1,
        "as_of": now.isoformat(),
        "market_status": trading_status(now.date()),
        "latest_attempt": latest["report_date"] if latest else None,
        "latest_attempt_status": latest["verification"]["status"] if latest else None,
        "latest_attempt_kind": latest["public_kind"] if latest else None,
        "last_valid_research": valid["report_date"] if valid else None,
        "current_research": current["report_date"] if current else None,
        "expires_at": current["expires_at"] if current else None,
    }
    (dist / "status.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    created.append(dist / "status.json")
    created.append(
        _render(
            env,
            "index.html",
            dist / "index.html",
            latest=latest,
            last_valid=valid,
            current=current,
            state=state,
            reports=reports[:10],
            config=config,
            asset_href="assets/style.css",
            latest_href="index.html",
            archive_href="reports/index.html",
        )
    )
    created.append(
        _render(
            env,
            "archive.html",
            dist / "reports" / "index.html",
            reports=reports,
            config=config,
            asset_href="../assets/style.css",
            latest_href="../index.html",
            archive_href="index.html",
        )
    )

    report_template = env.get_template("report.html")
    for report in reports:
        report_date = report["report_date"]
        destination = dist / "reports" / report_date / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            report_template.render(
                report=report,
                report_html=markdown_to_html(report["markdown"]) if report["valid"] else "",
                config=config,
                asset_href="../../assets/style.css",
                latest_href="../../index.html",
                archive_href="../index.html",
            ),
            encoding="utf-8",
        )
        created.append(destination)

    shutil.copyfile(
        config.site_templates_dir / "assets" / "style.css",
        dist / "assets" / "style.css",
    )
    created.append(dist / "assets" / "style.css")
    shutil.copyfile(
        config.site_templates_dir / "assets" / "status.js", dist / "assets" / "status.js"
    )
    created.append(dist / "assets" / "status.js")
    return created


def _render(env: Environment, template_name: str, path: Path, **context: object) -> Path:
    path.write_text(env.get_template(template_name).render(**context), encoding="utf-8")
    return path


def apply_publication_gate(report: dict, now: datetime) -> None:
    summary = report["summary"]
    report["valid"] = False
    report["current"] = False
    report["sources"] = []
    report["public_kind"] = "notice"
    report["kind_label"] = "검증 실패"
    report["notice"] = "검증을 통과한 연구 내용이 없어 후보와 점수를 표시하지 않습니다."
    previous = report["verification"]
    issues = public_artifact_issues(report["markdown"], summary, previous)
    if issues or previous.get("status") not in ("pass", "warning"):
        errors = [issue.message() for issue in issues] or stored_safety_messages(
            previous.get("errors")
        )
        report["verification"] = {
            "status": "fail",
            "errors": errors or ["저장된 보고서의 근거 검증 실패"],
            "warnings": [],
        }
        return
    try:
        context = context_from_summary(summary)
        if context.report_date != report["report_date"]:
            raise ValueError("report date mismatch")
        result = verify_report(context, report["markdown"])
        report["verification"] = result.model_dump()
        if result.status == "fail":
            return
        if context.market_context.get("market_status") == "missed":
            report["kind_label"] = "장전 발행 지연"
            report["notice"] = "장전 발행 마감이 지나 후보를 생성하지 않은 기록입니다."
            return
        if context.market_context.get("market_status") in {"closed", "unknown"}:
            report["kind_label"] = (
                "휴장 안내" if context.market_context["market_status"] == "closed"
                else "거래일 확인 필요"
            )
            report["notice"] = "휴장 안내" if context.market_context["market_status"] == "closed" \
                else "거래일 달력 확인 필요. 데이터 부족."
            return
        kst = ZoneInfo("Asia/Seoul")
        generated_kst = context.generated_at.astimezone(kst)
        now_kst = now.astimezone(kst)
        generated_date = generated_kst.date()
        matching_date = generated_date.isoformat() == report["report_date"]
        expiry = premarket_cutoff(generated_date)
        if (summary.get("run_mode") == "fixture"
                or context.market_context.get("run_mode") == "fixture"
                or any("mock" in source.source_name.lower()
                       or "example.com" in str(source.source_url) for source in context.sources)):
            report["kind_label"] = "테스트 자료"
            report["notice"] = "합성 테스트 자료입니다. 관찰 후보를 공개하지 않습니다."
            return
        calendar_status = trading_status(generated_date)
        if calendar_status == "closed" and matching_date:
            report["kind_label"] = report["notice"] = "휴장 안내"
            return
        if (not context.events
                or not matching_date
                or generated_kst >= expiry or generated_kst > now_kst
                or calendar_status != "open"):
            report["kind_label"] = "공개 제외"
            report["notice"] = "보관 기록입니다. 현재 장전 연구 자료로 제공하지 않습니다."
            return
        report["valid"] = True
        report["public_kind"] = "research" if summary.get("run_mode") == "live" else "legacy"
        report["kind_label"] = "검증된 연구 · 보관"
        report["expires_at"] = expiry.isoformat()
        report["current"] = (
            summary.get("run_mode") == "live"
            and summary.get("report_kind") == "research"
            and context.market_context.get("market_status") == "open"
            and generated_date == now_kst.date()
            and now_kst < expiry
        )
        report["summary"] = build_summary(context, report["markdown"], result.status)
        report["notice"] = (
            "당시 자료를 보존한 기록입니다. 현재 시세·오늘의 브리핑으로 사용하지 마세요."
        )
        by_source = {event.source_id: event.title for event in context.events}
        report["sources"] = [dict(
            source.model_dump(mode="json"),
            title=by_source.get(source.source_id, source.source_name)
        ) for source in context.sources if source.source_id in by_source]
    except (ValueError, KeyError, TypeError):
        report["valid"] = report["current"] = False
        report["public_kind"] = "notice"
        report["verification"] = {
            "status": "fail", "errors": ["보관 데이터 스키마 또는 근거 재검증 실패"], "warnings": []
        }


def _kst_display(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(
            ZoneInfo("Asia/Seoul")
        ).strftime("%Y-%m-%d %H:%M KST")
    except (ValueError, TypeError):
        return "데이터 부족"
