from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime

from openai import OpenAI

from daytrade_agent.config import AppConfig
from daytrade_agent.llm.codex_app_server import CodexAppServerSession
from daytrade_agent.llm.prompt_builder import build_prompt
from daytrade_agent.normalizers.event_schema import (
    Candidate,
    ReportContext,
    model_dump_json_safe,
    parse_datetime,
)


def write_report_markdown(
    config: AppConfig,
    context: ReportContext,
    *,
    dry_run: bool,
) -> str:
    prompt_path = config.root / "prompts" / "master_morning_briefing.md"
    prompt = build_prompt(context, prompt_path)

    if config.debug_artifacts_enabled and not dry_run:
        _write_private_debug(config, context.report_date, "prompt.md", prompt)

    if dry_run:
        context.market_context["writer_provider"] = "template_fixture"
        return _template_report(config, context, note="dry-run mock writer")

    provider = (config.env("REPORT_LLM_PROVIDER", "codex") or "codex").lower()
    if provider == "codex":
        response = _try_codex(prompt, config)
        if response:
            context.market_context["writer_provider"] = "codex"
            return response
        context.market_context["writer_provider"] = "template"
        context.market_context["writer_fallback"] = True
        return _template_report(config, context, note="codex unavailable; template fallback")

    if provider == "openai" and config.env("OPENAI_API_KEY"):
        response = _try_openai(prompt, config)
        if response:
            context.market_context["writer_provider"] = "openai"
            return response

    context.market_context["writer_provider"] = "template"
    return _template_report(config, context, note="llm unavailable; template fallback")


def build_summary(
    context: ReportContext,
    markdown: str,
    verification_status: str,
) -> dict[str, object]:
    publishable = verification_status != "fail" and bool(context.events)
    return {
        "report_date": context.report_date,
        "generated_at": context.generated_at.isoformat(),
        "data_as_of": _data_as_of(context),
        "data_status": context.data_status,
        "verification_status": verification_status,
        "run_mode": context.market_context.get("run_mode", "legacy"),
        "report_kind": "research" if publishable else "notice",
        "metrics": {
            "category_events": dict(Counter(event.category for event in context.events)),
            "grounded_candidates": len(context.candidates) if publishable else 0,
            "premarket_on_time": context.generated_at.hour < 9,
            "writer_fallback": context.market_context.get("writer_fallback", False),
            "writer_provider": context.market_context.get("writer_provider"),
        },
        "market_context": context.market_context,
        "missing_data": context.missing_data,
        "candidate_count": len(context.candidates) if publishable else 0,
        "top_event": _top_event(context) if publishable else {},
        "key_changes": [
            {"title": _event_text(event.title), "source_id": event.source_id,
             "published_at": event.published_at.isoformat() if event.published_at else None}
            for event in context.events[:3] if publishable
        ],
        "top_theme": _top_theme(context) if publishable else "데이터 부족",
        "top_risks": _top_risks(context) if publishable else [],
        "events": [model_dump_json_safe(event) for event in context.events if publishable],
        "candidates": [
            {
                "symbol": candidate.symbol,
                "name": candidate.name,
                "market": candidate.market,
                "categories": candidate.categories,
                "score": candidate.score,
                "main_reason": candidate.main_reason,
                "source_ids": candidate.source_ids,
                "data_key": candidate.price_snapshot.data_key if candidate.price_snapshot else None,
                "risk_flags": candidate.risk_flags,
                "observation_condition": candidate.observation_condition,
                "invalidation_condition": candidate.invalidation_condition,
            }
            for candidate in context.candidates if publishable
        ],
        "sources": [
            {
                "source_id": source.source_id,
                "source_name": source.source_name,
                "source_url": str(source.source_url) if source.source_url else None,
                "source_type": source.source_type,
                "published_at": source.published_at.isoformat() if source.published_at else None,
                "collected_at": source.collected_at.isoformat(),
                "source_quality": source.source_quality,
            }
            for source in context.sources if publishable
        ],
        "price_snapshots": [
            model_dump_json_safe(snapshot) for snapshot in context.price_snapshots if publishable
        ],
        "disclaimer": config_disclaimer(),
        "markdown_length": len(markdown),
    }


def _data_as_of(context: ReportContext) -> str:
    timestamps: list[datetime] = []
    for snapshot in context.price_snapshots:
        if snapshot.as_of:
            timestamps.append(snapshot.as_of)
    for value in context.market_context.values():
        if not isinstance(value, dict):
            continue
        raw_as_of = value.get("as_of")
        parsed = parse_datetime(str(raw_as_of)) if raw_as_of else None
        if parsed:
            timestamps.append(parsed)
    if not timestamps:
        return "데이터 부족"
    return max(timestamps).isoformat()


def _top_event(context: ReportContext) -> dict[str, object]:
    if not context.events:
        return {"title": "데이터 부족", "source_id": None, "category": None}
    event = sorted(
        context.events,
        key=lambda item: (item.confidence, item.source_quality),
        reverse=True,
    )[0]
    return {
        "title": event.title,
        "summary": event.summary,
        "category": event.category,
        "source_id": event.source_id,
        "data_status": event.data_status,
    }


def _top_theme(context: ReportContext) -> str:
    counter: Counter[str] = Counter()
    for event in context.events:
        if event.affected_sectors:
            counter.update(event.affected_sectors)
        else:
            counter[event.category] += 1
    if not counter:
        return "데이터 부족"
    return counter.most_common(1)[0][0]


def _top_risks(context: ReportContext) -> list[str]:
    risks: list[str] = []
    for candidate in context.candidates[:5]:
        risks.extend(flag for flag in candidate.risk_flags if flag != "none")
    return sorted(set(risks)) or ["데이터 부족"]


def config_disclaimer() -> str:
    return "이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다."


def failure_report_markdown(
    config: AppConfig,
    context: ReportContext,
    errors: list[str],
    warnings: list[str],
) -> str:
    lines = [
        f"# 데이터 검증 실패 리포트 - {context.report_date}",
        "",
        f"생성 시각: {context.generated_at.isoformat()}",
        "",
        f"> {config.disclaimer}",
        "",
        "## 검증 실패 이유",
        "",
    ]
    lines.extend(f"- {error}" for error in errors)
    if warnings:
        lines.extend(["", "## 경고", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "검증을 통과한 연구 내용이 없어 후보와 점수를 공개하지 않습니다.",
            "",
            "## 데이터 누락 및 확인 필요 사항",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in context.missing_data or ["데이터 부족"])
    lines.append("")
    return "\n".join(lines)


def market_closed_report_markdown(config: AppConfig, context: ReportContext) -> str:
    return "\n".join(
        [
            "# " + ("Market Closed Note" if context.market_context.get("market_status") == "closed"
                    else "거래일 확인 필요") + f" - {context.report_date}",
            "",
            f"생성 시각: {context.generated_at.isoformat()}",
            "",
            f"> {config.disclaimer}",
            "",
            "## 휴장 안내",
            "",
            "- 해당 날짜는 KRX 정규 거래일로 확인되지 않았습니다.",
            "- 데이터 부족: 장전 후보 수집과 가격 스냅샷 생성을 수행하지 않았습니다.",
            "",
            "## 확인 필요",
            "",
            "- 거래일은 XKRX 달력 및 검토된 변경 공지를 기준으로 판단합니다.",
            "",
        ]
    )


def _template_report(config: AppConfig, context: ReportContext, note: str) -> str:
    grouped = {category: [] for category in [
        "political_theme",
        "corporate_disclosure",
        "global_issue",
        "theme_surge",
    ]}
    for event in context.events:
        grouped[event.category].append(event)

    lines = [
        f"# K-Daytrade Morning Brief - {context.report_date}",
        "",
        f"생성 시각: {context.generated_at.isoformat()}",
        f"작성 경로: {note}",
        "",
        f"> {config.disclaimer}",
        "",
        "## 1. 5줄 핵심 요약",
        "",
    ]
    top = context.events[:5]
    if top:
        lines.extend(
            f"- {_event_text(event.title)} (source_id: {event.source_id})"
            for event in top
        )
    else:
        lines.append("- 데이터 부족")
    lines.extend(
        [
            "",
            "## 2. 시장 레짐",
            "",
            _market_context_text(context),
        ]
    )

    section_titles = {
        "political_theme": "3. 정치테마",
        "corporate_disclosure": "4. 기업공시",
        "global_issue": "5. 글로벌이슈",
        "theme_surge": "6. 테마급등",
    }
    for category, title in section_titles.items():
        lines.extend(["", f"## {title}", ""])
        events = grouped[category]
        if not events:
            lines.append("- 데이터 부족")
            continue
        for event in events[:5]:
            lines.append(
                f"- {_event_text(event.title)}: {_event_text(event.summary)} "
                f"(source_id: {event.source_id}, data_status: {event.data_status})"
            )

    lines.extend(["", "## 7. 통합 관심 후보 Top N", "", _candidate_table(context.candidates), ""])
    lines.extend(["## 8. 후보별 관찰 조건/트리거/무효화 조건/리스크", ""])
    for candidate in context.candidates:
        data_key = f"score_{candidate.symbol}"
        lines.append(
            f"- {candidate.name}({candidate.symbol}) | 관찰: {candidate.observation_condition} | "
            f"트리거: 공식 시세와 거래대금 재확인 후 변동성 관리 | "
            f"무효화: {candidate.invalidation_condition} | "
            f"리스크: {', '.join(candidate.risk_flags)} | data_key: {data_key}"
        )

    lines.extend(
        [
            "",
            "## 9. 주의 종목",
            "",
            _caution_text(context.candidates),
            "",
            "## 10. 오늘 주요 일정",
            "",
            "- 데이터 부족",
            "",
            "## 11. 데이터 누락 및 확인 필요 사항",
            "",
        ]
    )
    lines.extend(f"- {item} (data_key: report_metadata)"
                 for item in context.missing_data or ["데이터 부족"])
    lines.extend(["", "## 12. 투자 참고용 고지", "", config.disclaimer, ""])
    return "\n".join(lines)


def _try_openai(prompt: str, config: AppConfig) -> str | None:
    try:
        client = OpenAI(api_key=config.env("OPENAI_API_KEY"))
        response = client.responses.create(model=config.openai_model, input=prompt)
    except Exception:
        return None
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        if config.debug_artifacts_enabled:
            _write_private_debug(config, "latest", "openai_response.txt", output_text)
        return output_text.strip()
    return None


def _try_codex(prompt: str, config: AppConfig) -> str | None:
    model = config.env("CODEX_REPORT_MODEL", "gpt-5.5") or "gpt-5.5"
    timeout = float(config.env("CODEX_REQUEST_TIMEOUT", "180") or "180")
    workspace_dir = config.env(
        "CODEX_WORKSPACE_DIR",
        str(config.root / ".codex-report-workspace"),
    )
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    full_prompt = (
        "Return only JSON matching {\"answer\": \"markdown report\"}. "
        "The answer value must be the final public Markdown report.\n\n"
        f"{prompt}"
    )
    session = CodexAppServerSession(
        codex_binary=config.env("CODEX_BINARY"),
        request_timeout=timeout,
        workspace_dir=workspace_dir or str(config.root / ".codex-report-workspace"),
        cleanup_threads=True,
    )
    try:
        result = session.invoke(
            prompt=full_prompt,
            model=model,
            output_schema=schema,
            reasoning_effort=config.env("CODEX_REASONING_EFFORT", "medium"),
            summary=config.env("CODEX_SUMMARY", "none"),
            personality=config.env("CODEX_PERSONALITY", "none"),
        )
        payload = json.loads(_strip_json_fence(result.final_text))
    except Exception:
        return None
    finally:
        session.close()
    answer = payload.get("answer") if isinstance(payload, dict) else None
    return answer.strip() if isinstance(answer, str) and answer.strip() else None


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("```")
        if len(parts) >= 3:
            candidate = parts[1]
            if candidate.lstrip().startswith("json"):
                candidate = candidate.lstrip()[4:]
            return candidate.strip()
    return stripped


def _write_private_debug(config: AppConfig, report_date: str, filename: str, content: str) -> None:
    path = config.private_artifacts_dir / report_date / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _candidate_table(candidates: list[Candidate]) -> str:
    if not candidates:
        return "데이터 부족"
    lines = [
        "| 후보 | 점수 | 근거 | 리스크 |",
        "| --- | ---: | --- | --- |",
    ]
    for candidate in candidates:
        refs = "; ".join(f"source_id: {key}" for key in candidate.source_ids)
        data_key = f"score_{candidate.symbol}"
        lines.append(
            f"| {candidate.name}({candidate.symbol}) | {candidate.score:.2f} | "
            f"{refs}; data_key: {data_key} | {', '.join(candidate.risk_flags)} |"
        )
    return "\n".join(lines)


def _market_context_text(context: ReportContext) -> str:
    return "데이터 부족"


def _caution_text(candidates: list[Candidate]) -> str:
    caution = [candidate for candidate in candidates if candidate.risk_flags != ["none"]]
    if not caution:
        return "- 데이터 부족"
    return "\n".join(
        f"- {candidate.name}({candidate.symbol}): {', '.join(candidate.risk_flags)} "
        f"(data_key: score_{candidate.symbol})"
        for candidate in caution
    )


def _public_fact(text: str) -> str:
    from daytrade_agent.collectors.news_provider import _PUBLIC_REPLACEMENTS

    for original, replacement in _PUBLIC_REPLACEMENTS.items():
        text = text.replace(original, replacement)
    text = re.sub(r"매수\s*추천|강력\s*매수|즉시\s*매수|매수\s*하라", "가격 확인 필요", text)
    return text.replace("\n", " ").replace("|", "/")


def _event_text(text: str) -> str:
    from daytrade_agent.llm.report_verifier import PRICE_CONTEXT, PRICE_NUMBER

    if PRICE_CONTEXT.search(text) and PRICE_NUMBER.search(text):
        return "가격 관련 보도 수치 생략. 가격 확인 필요."
    return _public_fact(text)


def verified_facts_markdown(config: AppConfig, context: ReportContext) -> str:
    return _template_report(config, context, note="verified facts template")
