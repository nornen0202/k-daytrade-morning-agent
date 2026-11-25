from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from daytrade_agent.normalizers.event_schema import (
    MarketMetric,
    ReportContext,
    VerificationResult,
)
from daytrade_agent.normalizers.freshness import temporal_status

FORBIDDEN_TERMS = ["무조건 매수", "확실한 수익", "상한가 확정", "작전주", "세력주", "조작"]
PUBLIC_REPLACEMENTS = {
    "무조건 매수": "매수 강요 표현",
    "확실한 수익": "수익 보장성 표현",
    "상한가 확정": "가격 급등 확정 표현",
    "작전주": "근거 부족 테마",
    "세력주": "수급 집중 관련 표현",
    "조작": "보도 기준 의혹",
    "계좌": "금융계정 관련 표현",
    "보유비중": "비중 정보",
}
INVESTMENT_PRESSURE_PATTERNS = [re.compile(pattern) for pattern in (
    r"매수\s*하라", r"수익\s*보장", r"상한가\s*확정", r"즉시\s*매수",
    r"매수\s*추천", r"진입\s*하라", r"강력\s*매수",
)]
CREDENTIAL_PATTERNS = [re.compile(pattern, re.I) for pattern in (
    r"sk-[A-Za-z0-9_-]{20,}",
    r"(?:api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_-]{12,}",
    r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}",
)]
ACCOUNT_PATTERNS = [re.compile(pattern, re.I) for pattern in (
    r"\b\d{3,6}-\d{3,6}-\d{4,10}\b",
    r"(?:계좌번호|실제\s*보유\s*비중|보유수량)\s*[:=]?\s*\d+",
)]
SECRET_PATTERNS = [*CREDENTIAL_PATTERNS, *ACCOUNT_PATTERNS]
PUBLIC_TEXT_REASONS = {
    "encoding_replacement": "unreadable text encoding",
    "prohibited_wording": "prohibited wording found",
    "investment_pressure": "investment-pressure wording found",
    "credential_pattern": "possible secret or account-like identifier found",
    "account_like_identifier": "possible secret or account-like identifier found",
}
REF_PATTERN = re.compile(r"(source_id|data_key):\s*([A-Za-z0-9_-]+)")
SYMBOL_PATTERN = re.compile(r"(?<![-:\d.])\b\d{6}\b(?![-:\d])")
NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z_\d])([+-]?\d[\d,]*(?:\.\d+)?)\s*"
    r"((?:조|억|만|천)?\s*(?:원|달러|%|주|배|명|건|년|월|일|시|분기|분|포인트|bp))?"
)
ISO_DATE_PATTERN = re.compile(
    r"(?<![A-Za-z_\d-])\d{4}-\d{2}-\d{2}"
    r"(?:[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:?\d{2})?)?"
    r"(?![\d:-])"
)
PRICE_CONTEXT = re.compile(r"현재가|주가|시세|등락률|전일대비|거래대금|last_price|change_rate")
PRICE_NUMBER = re.compile(r"[+-]?\d[\d,.]*\s*(?:원|%|달러)")
CERTAINTY_ASSERTION = re.compile(
    r"확정(?:이(?:다|고|며)|입니다|됐|되었|된다|됩니다|했|한다|합니다|할\s*것)"
    r"|분명(?:하다|합니다|히\s*(?:상승|수익))|반드시.*상승"
    r"|(?:상승|하락|수익|이익|방향|국면)\s*(?:은|는|이|가)?\s*확정"
    r"(?!할\s*수\s*없|하지\s*않|하지\s*못|이\s*아니)"
)
MARKET_CERTAINTY_ASSERTION = re.compile(
    r"확정(?:이(?:다|고|며)|입니다|할\s*것)"
    r"|분명히\s*(?:상승|하락|수익)|반드시.*상승"
    r"|(?:상승|하락|수익|이익|방향|국면)\s*(?:은|는|이|가)?\s*확정"
    r"(?!할\s*수\s*없|하지\s*않|하지\s*못|이\s*아니)"
)
_OBFUSCATED_TERM_PATTERNS = [
    (re.compile(r"\s*".join(re.escape(ch) for ch in term.replace(" ", ""))), replacement)
    for term, replacement in PUBLIC_REPLACEMENTS.items()
    if term in FORBIDDEN_TERMS
]


def sanitize_public_text(text: str, *, mask_symbols: bool = False) -> str:
    """Normalize and redact prohibited, secret, or spoofed-reference text for public output."""
    sanitized = _normalized(text).replace("\r", " ").replace("\n", " ").replace("|", "/")
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[비공개 정보 제외]", sanitized)
    for original, replacement in PUBLIC_REPLACEMENTS.items():
        sanitized = sanitized.replace(original, replacement)
    for pattern, replacement in _OBFUSCATED_TERM_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    for pattern in INVESTMENT_PRESSURE_PATTERNS:
        sanitized = pattern.sub("가격 확인 필요", sanitized)
    sanitized = REF_PATTERN.sub(r"\1_ref_\2", sanitized)
    if mask_symbols:
        sanitized = SYMBOL_PATTERN.sub("종목코드 확인 필요", sanitized)
    return re.sub(r"\s{2,}", " ", sanitized).strip()


def unsafe_public_text(text: str) -> bool:
    return bool(public_text_reasons(text))


def public_text_reasons(text: str) -> tuple[str, ...]:
    text = _normalized(text)
    compact = re.sub(r"\s+", "", text)
    matched = {
        "encoding_replacement": "\ufffd" in text,
        "prohibited_wording": any(term.replace(" ", "") in compact for term in FORBIDDEN_TERMS),
        "investment_pressure": any(
            pattern.search(text) for pattern in INVESTMENT_PRESSURE_PATTERNS
        ),
        "credential_pattern": any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS),
        "account_like_identifier": any(pattern.search(text) for pattern in ACCOUNT_PATTERNS),
    }
    return tuple(code for code, found in matched.items() if found)


def _normalized(text: str) -> str:
    return re.sub(r"[\u200b-\u200f\ufeff]", "", unicodedata.normalize("NFKC", text))


def _numeric_claims(text: str) -> set[tuple[Decimal | str, str]]:
    text = REF_PATTERN.sub("", text)
    text = re.sub(r"https?://\S+", "", text)
    dates = {(stamp.replace(" ", "T").upper(), "iso_date")
             for stamp in ISO_DATE_PATTERN.findall(text)}
    # A timestamp can also support its own calendar date, but never its component numbers.
    dates.update((stamp[:10], unit) for stamp, unit in tuple(dates))
    numbers = NUMBER_PATTERN.findall(ISO_DATE_PATTERN.sub(" ", text))
    return dates | {(Decimal(number.replace(",", "")), re.sub(r"\s", "", unit))
                    for number, unit in numbers}


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
                f"{candidate.name} {candidate.symbol} {candidate.score:.2f}/10 "
                f"{candidate.observation_condition} {candidate.invalidation_condition}"
            )
    for metric_name, raw_metric in context.market_context.items():
        if (
            metric_name not in {"kospi", "kosdaq", "usdkrw", "sp500", "nasdaq"}
            or not isinstance(raw_metric, dict)
        ):
            continue
        try:
            metric = MarketMetric.model_validate(raw_metric)
        except ValueError:
            continue
        if temporal_status(metric.as_of, context.generated_at, 96) != "ok":
            continue
        change_part = f" {metric.change_rate}%" if metric.change_rate is not None else ""
        evidence[("data_key", metric.data_key)] = (
            f"{metric_name} {metric.value}{change_part} {metric.as_of.isoformat()}"
        )
    evidence[("data_key", "report_metadata")] = (
        f"{context.report_date} {context.generated_at.isoformat()} "
        + " ".join(context.missing_data)
    )
    return evidence


def verify_report(context: ReportContext, markdown: str) -> VerificationResult:
    errors = [PUBLIC_TEXT_REASONS[code] for code in public_text_reasons(markdown)]
    markdown = _normalized(markdown)
    warnings: list[str] = []
    known_symbols = (
        {candidate.symbol for candidate in context.candidates}
        | {symbol for event in context.events for symbol in event.candidate_symbols}
        | {snapshot.symbol for snapshot in context.price_snapshots}
    )
    unknown = set(SYMBOL_PATTERN.findall(REF_PATTERN.sub("", markdown))) - known_symbols
    if unknown:
        errors.append("unknown symbol mentioned")

    evidence = evidence_index(context)
    snapshots = {snapshot.data_key: snapshot for snapshot in context.price_snapshots}
    for number, line in enumerate(markdown.splitlines(), 1):
        refs = REF_PATTERN.findall(line)
        for ref_type, key in refs:
            if (ref_type, key) not in evidence:
                errors.append(f"line {number}: unknown or unusable {ref_type} referenced")
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
            if (
                heading == "5줄 핵심 요약"
                or heading in titles
                or re.fullmatch(r"통합 관심 후보 Top \d+", heading)
                or not _numeric_claims(heading)
            ):
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
        if text.startswith("|") and not _numeric_claims(text) and not refs:
            continue
        if text in {"- 데이터 부족", "데이터 부족", "가격 확인 필요"}:
            continue
        if context.market_context.get("market_status") in {"closed", "unknown"}:
            if not _numeric_claims(text) and not refs:
                continue
        if text == "이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.":
            continue
        if not refs:
            label = "numeric material claim" if _numeric_claims(text) else "material claim"
            errors.append(f"line {number}: {label} lacks source_id or data_key")
        else:
            supported = set().union(*(
                _numeric_claims(evidence.get(tuple(ref), "")) for ref in refs
            ))
            supported |= {(Decimal(symbol), "") for symbol in known_symbols if symbol.isdigit()}
            if _numeric_claims(text) - supported:
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

        if context.data_status != "ok" and (
            MARKET_CERTAINTY_ASSERTION.search(text)
            or (CERTAINTY_ASSERTION.search(text) and "데이터 부족" in text)
        ):
            errors.append(f"line {number}: certainty wording used with insufficient data")

    if context.data_status != "ok" and context.market_context.get("market_status") != "closed":
        warnings.append(f"report data_status is {context.data_status}")
    if context.missing_data and context.market_context.get("market_status") != "closed":
        warnings.append("missing data was reported")
    status = "fail" if errors else "warning" if warnings else "pass"
    return VerificationResult(status=status, errors=sorted(set(errors)), warnings=warnings)
