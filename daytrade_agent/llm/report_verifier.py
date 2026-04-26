from __future__ import annotations

import re

from daytrade_agent.normalizers.event_schema import ReportContext, VerificationResult

DATA_GAP_TEXT = "\ub370\uc774\ud130 \ubd80\uc871"
MARKET_CLOSED_TEXT = "\ud734\uc7a5"

FORBIDDEN_TERMS = [
    "\ubb34\uc870\uac74" + " " + "\ub9e4\uc218",
    "\ud655\uc2e4\ud55c" + " " + "\uc218\uc775",
    "\uc791\uc804" + "\uc8fc",
    "\uc138\ub825" + "\uc8fc",
    "\uc870" + "\uc791",
]

INVESTMENT_PRESSURE_PATTERNS = [
    re.compile(r"\ub9e4\uc218\s*\ud558\ub77c"),
    re.compile(r"\uc218\uc775\s*\ubcf4\uc7a5"),
    re.compile(r"\uc0c1\ud55c\uac00\s*\ud655\uc815"),
    re.compile(r"\uc989\uc2dc\s*\ub9e4\uc218"),
    re.compile(r"\ub9e4\uc218\s*\ucd94\ucc9c"),
    re.compile(r"\uc9c4\uc785\s*\ud558\ub77c"),
    re.compile(r"\uac15\ub825\s*\ub9e4\uc218"),
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\b\d{3,6}-\d{3,6}-\d{4,10}\b"),
]

CERTAINTY_PATTERNS = [
    re.compile(DATA_GAP_TEXT + r".*\ud655\uc815"),
    re.compile(DATA_GAP_TEXT + r".*\ubd84\uba85"),
    re.compile(r"insufficient.*confirmed", re.IGNORECASE),
]
PRICE_LIKE_PATTERN = re.compile(r"\d[\d,]*(?:\uc6d0|%)")
SYMBOL_PATTERN = re.compile(r"(?<![-:\d.])\b\d{6}\b(?![-:\d])")


def verify_report(context: ReportContext, markdown: str) -> VerificationResult:
    errors: list[str] = []
    warnings: list[str] = []

    _check_forbidden_terms(markdown, errors)
    _check_symbols(context, markdown, errors)
    _check_price_claims(context, markdown, errors)
    _check_sources(context, markdown, errors)
    _check_source_less_numeric_claims(markdown, errors)
    _check_certainty(markdown, errors)
    _check_data_status(context, warnings)

    status = "fail" if errors else "warning" if warnings else "pass"
    return VerificationResult(status=status, errors=errors, warnings=warnings)


def _check_forbidden_terms(markdown: str, errors: list[str]) -> None:
    for term in FORBIDDEN_TERMS:
        if term in markdown:
            errors.append("prohibited wording found")
    for pattern in INVESTMENT_PRESSURE_PATTERNS:
        if pattern.search(markdown):
            errors.append("investment-pressure wording found")
    for pattern in SECRET_PATTERNS:
        if pattern.search(markdown):
            errors.append("possible secret or account-like identifier found")


def _check_symbols(context: ReportContext, markdown: str, errors: list[str]) -> None:
    known_symbols = {candidate.symbol for candidate in context.candidates}
    known_symbols.update(symbol for event in context.events for symbol in event.candidate_symbols)
    observed_symbols = set(SYMBOL_PATTERN.findall(markdown))
    unknown = sorted(observed_symbols - known_symbols)
    if unknown:
        errors.append(f"unknown symbol mentioned: {', '.join(unknown)}")


def _check_price_claims(context: ReportContext, markdown: str, errors: list[str]) -> None:
    data_keys = {
        candidate.price_snapshot.data_key
        for candidate in context.candidates
        if candidate.price_snapshot is not None
    }
    price_lines = [
        line
        for line in markdown.splitlines()
        if PRICE_LIKE_PATTERN.search(line) and not line.startswith("#")
    ]
    for line in price_lines:
        if "data_key:" not in line and not any(data_key in line for data_key in data_keys):
            errors.append("price-like claim lacks price_snapshot data_key")
            return


def _check_sources(context: ReportContext, markdown: str, errors: list[str]) -> None:
    source_ids = {source.source_id for source in context.sources}
    candidate_sources = {
        source_id for candidate in context.candidates for source_id in candidate.source_ids
    }
    valid_sources = source_ids | candidate_sources
    source_mentions = set(re.findall(r"source_id:\s*([A-Za-z0-9_\-]+)", markdown))
    unknown = sorted(source_mentions - valid_sources)
    if unknown:
        errors.append(f"unknown source_id referenced: {', '.join(unknown)}")

    key_sections = [
        "\ud575\uc2ec \uc694\uc57d",
        "\uc815\uce58\ud14c\ub9c8",
        "\uae30\uc5c5\uacf5\uc2dc",
        "\uae00\ub85c\ubc8c\uc774\uc288",
        "\ud14c\ub9c8\uae09\ub4f1",
    ]
    for line in markdown.splitlines():
        if not line.startswith("- "):
            continue
        if any(section in line for section in key_sections) and DATA_GAP_TEXT not in line:
            if "source_id:" not in line and "data_key:" not in line:
                errors.append("material bullet lacks source_id or data_key")
                return


def _check_source_less_numeric_claims(markdown: str, errors: list[str]) -> None:
    for line in markdown.splitlines():
        stripped = line.strip()
        if not _is_material_claim_line(stripped):
            continue
        if (
            DATA_GAP_TEXT in stripped
            or MARKET_CLOSED_TEXT in stripped
            or "market_closed" in stripped
        ):
            continue
        if not re.search(r"\d", stripped):
            continue
        if "source_id:" not in stripped and "data_key:" not in stripped:
            errors.append("numeric material claim lacks source_id or data_key")
            return


def _is_material_claim_line(line: str) -> bool:
    if line.startswith("- "):
        return True
    if line.startswith("|") and "---" not in line:
        return True
    return False


def _check_certainty(markdown: str, errors: list[str]) -> None:
    for pattern in CERTAINTY_PATTERNS:
        if pattern.search(markdown):
            errors.append("certainty wording used with insufficient data")


def _check_data_status(context: ReportContext, warnings: list[str]) -> None:
    if context.data_status != "ok":
        warnings.append(f"report data_status is {context.data_status}")
    if context.missing_data:
        warnings.append("missing data was reported")
