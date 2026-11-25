from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlsplit

from daytrade_agent.llm.report_verifier import PUBLIC_TEXT_REASONS, public_text_reasons
from daytrade_agent.normalizers.event_schema import (
    Candidate,
    MarketEvent,
    MarketMetric,
    PriceSnapshot,
    ReportContext,
    Source,
    VerificationResult,
)

_PRIVATE_FIELDS = {
    "raw_response", "raw_prompt", "access_token", "refresh_token", "authorization",
    "account_number", "holdings", "api_key", "apikey", "app_secret", "client_secret",
    "private_key", "secret", "token", "password",
}
_PUBLIC_FIELDS = _PRIVATE_FIELDS | {
    key
    for model in (Candidate, MarketEvent, MarketMetric, PriceSnapshot, ReportContext, Source,
                  VerificationResult)
    for key in model.model_fields
} | {
    "data_as_of", "verification_status", "run_mode", "report_kind", "metrics", "category_events",
    "grounded_candidates", "premarket_on_time", "writer_fallback", "writer_provider",
    "writer_model", "rejected_writer_model", "market_status", "candidate_count", "top_event",
    "key_changes", "top_theme", "top_risks", "disclaimer", "markdown_length", "calendar_provider",
    "kospi", "kosdaq", "usdkrw", "sp500", "nasdaq",
}
_CODES = PUBLIC_TEXT_REASONS.keys() | {
    "configured_credential", "private_payload_field", "credential_url", "invalid_url",
    "invalid_schema",
}
_PATH_PART = re.compile(r"(\*|[a-z_][a-z_0-9]*)(?:\[\])*")


@dataclass(frozen=True, order=True)
class PublicSafetyIssue:
    field: str
    code: str

    def message(self) -> str:
        return f"public_safety field={self.field} code={self.code}"


class PublicSafetyError(ValueError):
    def __init__(self, issues: list[PublicSafetyIssue]):
        self.issues = issues
        super().__init__(", ".join(issue.message() for issue in issues))


def public_artifact_issues(
    markdown: str, summary: dict, verification: dict | None = None,
) -> list[PublicSafetyIssue]:
    credentials = {
        value for name, value in os.environ.items()
        if len(value) >= 8 and any(
            marker in name.upper()
            for marker in ("API_KEY", "APP_KEY", "SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY")
        )
    }
    issues: set[PublicSafetyIssue] = set()

    def check_text(value: str, field: str) -> None:
        variants = (value,)
        if field.endswith(".source_url"):
            try:
                url = urlsplit(value)
                keys = {key.casefold() for key, _ in parse_qsl(url.query, keep_blank_values=True)}
                if url.username is not None or keys & _PRIVATE_FIELDS:
                    issues.add(PublicSafetyIssue(field, "credential_url"))
            except ValueError:
                issues.add(PublicSafetyIssue(field, "invalid_url"))
            # Inspect escaped credentials as well as the literal URL. Legacy URL encodings
            # can contain non-UTF-8 escapes, which are separate from corrupt display text.
            variants += (unquote(value, errors="ignore"),)
        for text in variants:
            issues.update(PublicSafetyIssue(field, code) for code in public_text_reasons(text))
            if any(secret in text for secret in credentials):
                issues.add(PublicSafetyIssue(field, "configured_credential"))

    def walk(value: object, field: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = key.casefold()
                child_field = f"{field}.{lowered if lowered in _PUBLIC_FIELDS else '*'}"
                if lowered in _PRIVATE_FIELDS:
                    issues.add(PublicSafetyIssue(child_field, "private_payload_field"))
                check_text(key, f"{field}.*")
                walk(child, child_field)
        elif isinstance(value, list):
            for child in value:
                walk(child, f"{field}[]")
        elif isinstance(value, str):
            check_text(value, field)

    check_text(markdown, "markdown")
    walk(summary, "summary")
    if verification is not None:
        walk(verification, "verification")
    return sorted(issues)


def stored_safety_messages(errors: object) -> list[str]:
    """Allow only bounded field names and reason codes from untrusted stored diagnostics."""
    if not isinstance(errors, list):
        return []
    result = []
    for message in errors:
        if not isinstance(message, str) or not message.startswith("public_safety field="):
            continue
        field, _, code = message.removeprefix("public_safety field=").partition(" code=")
        root, *parts = field.split(".")
        if root not in {"summary", "markdown", "verification"} or code not in _CODES:
            continue
        if all((match := _PATH_PART.fullmatch(part))
               and (match[1] == "*" or match[1] in _PUBLIC_FIELDS) for part in parts):
            result.append(message)
    return sorted(set(result))
