from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from daytrade_agent.normalizers.event_schema import ReportContext, VerificationResult
from daytrade_agent.normalizers.freshness import temporal_status

FORBIDDEN_TERMS = ["무조건 매수", "확실한 수익", "상한가 확정", "작전주", "세력주", "조작"]
INVESTMENT_PRESSURE_PATTERNS = [re.compile(pattern) for pattern in (
    r"매수\s*하라", r"수익\s*보장", r"상한가\s*확정", r"즉시\s*매수",
    r"매수\s*추천", r"진입\s*하라", r"강력\s*매수",
)]
SECRET_PATTERNS = [re.compile(pattern, re.I) for pattern in (
    r"sk-[A-Za-z0-9_-]{20,}",
    r"(?:api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_-]{12,}",
    r"\b\d{3,6}-\d{3,6}-\d{4,10}\b",
    r"(?:계좌번호|실제\s*보유\s*비중|보유수량)\s*[:=]?\s*\d+",
    r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}",
)]
REF_PATTERN = re.compile(r"(source_id|data_key):\s*([A-Za-z0-9_-]+)")
SYMBOL_PATTERN = re.compile(r"(?<![-:\d.])\b\d{6}\b(?![-:\d])")
NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z_\d])([+-]?\d[\d,]*(?:\.\d+)?)\s*"
    r"((?:조|억|만|천)?\s*(?:원|달러|%|주|배|명|건|년|월|일|시|분|포인트|bp))?"
)
PRICE_CONTEXT = re.compile(r"현재가|주가|시세|등락률|전일대비|거래대금|last_price|change_rate")
PRICE_NUMBER = re.compile(r"[+-]?\d[\d,.]*\s*(?:원|%|달러)")
CERTAINTY_ASSERTION = re.compile(
    r"확정(?:이(?:다|고|며)|입니다|됐|되었|된다|됩니다|했|한다|합니다|할\s*것)"
    r"|분명(?:하다|합니다|히\s*(?:상승|수익))|반드시.*상승"
    r"|(?:상승|하락|수익|이익|방향|국면)\s*(?:은|는|이|가)?\s*확정"
    r"(?!할\s*수\s*없|하지\s*않|하지\s*못|이\s*아니)"
)


def unsafe_public_text(text: str) -> bool:
    text = _normalized(text)
    compact = re.sub(r"\s+", "", text)
    return bool("\ufffd" in text or any(term.replace(" ", "") in compact
                                      for term in FORBIDDEN_TERMS)
                or any(pattern.search(text) for pattern in
                       [*INVESTMENT_PRESSURE_PATTERNS, *SECRET_PATTERNS]))


def _normalized(text: str) -> str:
    return re.sub(r"[\u200b-\u200f\ufeff]", "", unicodedata.normalize("NFKC", text))


def _numbers(text: str) -> set[tuple[Decimal, str]]:
    text = REF_PATTERN.sub("", text)
    text = re.sub(r"https?://\S+", "", text)
    return {(Decimal(number.replace(",", "")), re.sub(r"\s", "", unit))
            for number, unit in NUMBER_PATTERN.findall(text)}


def evidence_index(context: ReportContext) -> dict[tuple[str, str], str]:
    sources = {source.source_id: source for source in context.sources}
    evidence: dict[tuple[str, str], str] = {}
    for event in context.events:
        source = sources.get(event.source_id)
        if (source is None or event.data_status in {"stale", "insufficient"}
                or temporal_status(event.published_at, context.generated_at) != "ok"
                or temporal_status(source.published_at, context.generated_at) != "ok"
                or temporal_status(source.collected_at, context.generated_at) != "ok"):
            continue
        key = ("source_id", event.source_id)
        evidence[key] = evidence.get(key, "") + (
            f" {event.title} {event.summary} {event.published_at.isoformat()}"
        )
    for snapshot in context.price_snapshots:
        if (snapshot.data_status in {"stale", "insufficient"}
                or temporal_status(snapshot.as_of, context.generated_at, 96) != "ok"):
            continue
        evidence[("data_key", snapshot.data_key)] = (
            f"{snapshot.symbol} {snapshot.as_of.isoformat()} "
            f"{snapshot.last_price}원 {snapshot.change_rate}% "
            f"{snapshot.volume}주 {snapshot.trading_value}원"
        )
    for candidate in context.candidates:
        if candidate.source_ids and all(("source_id", key) in evidence
                                        for key in candidate.source_ids):
            evidence[("data_key", f"score_{candidate.symbol}")] = (
                f"{candidate.symbol} {candidate.score:.2f}/10 "
                f"{candidate.observation_condition} {candidate.invalidation_condition}"
            )
    evidence[("data_key", "report_metadata")] = (
        f"{context.report_date} {context.generated_at.isoformat()} "
        + " ".join(context.missing_data)
    )
    return evidence


def verify_report(context: ReportContext, markdown: str) -> VerificationResult:
    markdown = _normalized(markdown)
    errors: list[str] = []
    warnings: list[str] = []
    if any(term.replace(" ", "") in re.sub(r"\s+", "", markdown) for term in FORBIDDEN_TERMS):
        errors.append("prohibited wording found")
    if any(pattern.search(markdown) for pattern in INVESTMENT_PRESSURE_PATTERNS):
        errors.append("investment-pressure wording found")
    if any(pattern.search(markdown) for pattern in SECRET_PATTERNS):
        errors.append("possible secret or account-like identifier found")
    if "\ufffd" in markdown:
        errors.append("unreadable text encoding")
    known_symbols = {candidate.symbol for candidate in context.candidates}
    unknown = set(SYMBOL_PATTERN.findall(REF_PATTERN.sub("", markdown))) - known_symbols
    if unknown:
        errors.append(f"unknown symbol mentioned: {', '.join(sorted(unknown))}")

    evidence = evidence_index(context)
    snapshots = {snapshot.data_key: snapshot for snapshot in context.price_snapshots}
    for number, line in enumerate(markdown.splitlines(), 1):
        refs = REF_PATTERN.findall(line)
        for ref_type, key in refs:
            if (ref_type, key) not in evidence:
                errors.append(f"line {number}: unknown or unusable {ref_type} referenced: {key}")
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            heading = re.sub(r"^#+\s*(?:\d+\.\s*)?", "", text)
            titles = {
                f"K-Daytrade Morning Brief - {context.report_date}",
                f"Market Closed Note - {context.report_date}",
                f"거래일 확인 필요 - {context.report_date}",
                f"장전 발행 지연 안내 - {context.report_date}",
            }
            if (heading == "5줄 핵심 요약" or heading in titles
                    or not _numbers(heading)):
                continue
        if text.startswith("> ") and text[2:] == (
            "이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다."
        ):
            continue
        if re.fullmatch(r"\|[\s|:\-]+\|", text):
            continue
        if text == f"생성 시각: {context.generated_at.isoformat()}":
            continue
        if re.fullmatch(r"작성 경로: [A-Za-z ;_-]+", text):
            continue
        if text.startswith("|") and not _numbers(text) and not refs:
            continue
        if text in {"- 데이터 부족", "데이터 부족", "가격 확인 필요"}:
            continue
        if context.market_context.get("market_status") in {"closed", "unknown"}:
            if not _numbers(text) and not refs:
                continue
        if text == "이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.":
            continue
        if not refs:
            label = "numeric material claim" if _numbers(text) else "material claim"
            errors.append(f"line {number}: {label} lacks source_id or data_key")
        else:
            supported = set().union(*(_numbers(evidence.get(tuple(ref), "")) for ref in refs))
            supported |= {(Decimal(symbol), "") for symbol in known_symbols if symbol.isdigit()}
            if _numbers(text) - supported:
                errors.append(f"line {number}: numeric value or unit not present in cited evidence")

        quoted_subject = bool(PRICE_CONTEXT.search(text)) or any(
            candidate.name in text or candidate.symbol in text for candidate in context.candidates
        )
        if quoted_subject and PRICE_NUMBER.search(text):
            price_refs = [snapshots[key] for kind, key in refs
                          if kind == "data_key" and key in snapshots
                          and (kind, key) in evidence]
            if not price_refs:
                errors.append(f"line {number}: price-like claim lacks price_snapshot data_key")
            elif not any(snapshot.as_of.isoformat() in text for snapshot in price_refs):
                errors.append(f"line {number}: price timestamp missing from claim")
            elif SYMBOL_PATTERN.search(text) and not any(
                snapshot.symbol in SYMBOL_PATTERN.findall(text) for snapshot in price_refs
            ):
                errors.append(f"line {number}: price snapshot belongs to a different symbol")

        if (context.data_status != "ok" and CERTAINTY_ASSERTION.search(text)
                and "데이터 부족" in text):
            errors.append(f"line {number}: certainty wording used with insufficient data")

    if context.data_status != "ok" and context.market_context.get("market_status") != "closed":
        warnings.append(f"report data_status is {context.data_status}")
    if context.missing_data and context.market_context.get("market_status") != "closed":
        warnings.append("missing data was reported")
    status = "fail" if errors else "warning" if warnings else "pass"
    return VerificationResult(status=status, errors=sorted(set(errors)), warnings=warnings)
