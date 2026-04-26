from __future__ import annotations

import json

from openai import OpenAI

from daytrade_agent.config import AppConfig
from daytrade_agent.llm.codex_app_server import CodexAppServerSession
from daytrade_agent.llm.prompt_builder import build_prompt
from daytrade_agent.normalizers.event_schema import Candidate, ReportContext, model_dump_json_safe


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
        return _template_report(config, context, note="dry-run mock writer")

    provider = (config.env("REPORT_LLM_PROVIDER", "codex") or "codex").lower()
    if provider == "codex":
        response = _try_codex(prompt, config)
        if response:
            return response
        return _template_report(config, context, note="codex unavailable; template fallback")

    if provider == "openai" and config.env("OPENAI_API_KEY"):
        response = _try_openai(prompt, config)
        if response:
            return response

    return _template_report(config, context, note="llm unavailable; template fallback")


def build_summary(
    context: ReportContext,
    markdown: str,
    verification_status: str,
) -> dict[str, object]:
    return {
        "report_date": context.report_date,
        "generated_at": context.generated_at.isoformat(),
        "data_status": context.data_status,
        "verification_status": verification_status,
        "market_context": context.market_context,
        "missing_data": context.missing_data,
        "candidate_count": len(context.candidates),
        "events": [model_dump_json_safe(event) for event in context.events],
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
            for candidate in context.candidates
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
            for source in context.sources
        ],
        "price_snapshots": [
            model_dump_json_safe(snapshot) for snapshot in context.price_snapshots
        ],
        "disclaimer": config_disclaimer(),
        "markdown_length": len(markdown),
    }


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
            "## 공개 가능한 후보 요약",
            "",
            _candidate_table(context.candidates),
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
            f"# Market Closed Note - {context.report_date}",
            "",
            f"생성 시각: {context.generated_at.isoformat()}",
            "",
            f"> {config.disclaimer}",
            "",
            "## 휴장 안내",
            "",
            "- market_closed: 해당 날짜는 KRX 정규 거래일로 확인되지 않았습니다.",
            "- 데이터 부족: 장전 후보 수집과 가격 스냅샷 생성을 수행하지 않았습니다.",
            "",
            "## 확인 필요",
            "",
            "- config/holidays_kr.yml을 운영 환경에 맞게 관리하세요.",
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
    top = context.candidates[:5]
    if top:
        lines.extend(
            f"- {candidate.name}({candidate.symbol}) 관찰 우선순위 {candidate.score:.2f}/10 "
            f"- source_id: {', '.join(candidate.source_ids)}"
            for candidate in top
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
        for event in events:
            lines.append(
                f"- {event.title}: {event.summary} "
                f"(source_id: {event.source_id}, data_status: {event.data_status})"
            )

    lines.extend(["", "## 7. 통합 관심 후보 Top N", "", _candidate_table(context.candidates), ""])
    lines.extend(["## 8. 후보별 관찰 조건/트리거/무효화 조건/리스크", ""])
    for candidate in context.candidates:
        data_key = candidate.price_snapshot.data_key if candidate.price_snapshot else "데이터 부족"
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
    lines.extend(f"- {item}" for item in context.missing_data or ["데이터 부족"])
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
        refs = ", ".join(candidate.source_ids)
        data_key = candidate.price_snapshot.data_key if candidate.price_snapshot else "데이터 부족"
        lines.append(
            f"| {candidate.name}({candidate.symbol}) | {candidate.score:.2f} | "
            f"source_id: {refs}; data_key: {data_key} | {', '.join(candidate.risk_flags)} |"
        )
    return "\n".join(lines)


def _market_context_text(context: ReportContext) -> str:
    if not context.market_context:
        return "데이터 부족"
    return json.dumps(context.market_context, ensure_ascii=False, sort_keys=True)


def _caution_text(candidates: list[Candidate]) -> str:
    caution = [candidate for candidate in candidates if candidate.risk_flags != ["none"]]
    if not caution:
        return "- 데이터 부족"
    return "\n".join(
        f"- {candidate.name}({candidate.symbol}): {', '.join(candidate.risk_flags)} "
        f"(source_id: {', '.join(candidate.source_ids)})"
        for candidate in caution
    )
