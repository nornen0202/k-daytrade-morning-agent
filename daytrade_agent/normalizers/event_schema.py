from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from daytrade_agent.config import KST_TIMEZONE

EventCategory = Literal["political_theme", "corporate_disclosure", "global_issue", "theme_surge"]
DataStatus = Literal["ok", "partial", "insufficient", "stale"]
VerificationStatus = Literal["pass", "fail", "warning"]


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Source(StrictBaseModel):
    source_id: str
    source_name: str
    source_url: HttpUrl | None = None
    source_type: str = "news"
    published_at: datetime | None = None
    collected_at: datetime
    source_quality: float = Field(default=0.5, ge=0, le=1)


class MarketEvent(StrictBaseModel):
    event_id: str
    category: EventCategory
    title: str
    summary: str
    published_at: datetime | None = None
    source_id: str
    source_url: HttpUrl | None = None
    source_name: str
    source_quality: float = Field(default=0.5, ge=0, le=1)
    affected_sectors: list[str] = Field(default_factory=list)
    candidate_symbols: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    data_status: DataStatus = "ok"

    @field_validator("candidate_symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        return [symbol.strip() for symbol in value if symbol and symbol.strip()]


class PriceSnapshot(StrictBaseModel):
    symbol: str
    name: str
    market: str = "KOSPI"
    last_price: float | None = Field(default=None, ge=0)
    change_rate: float | None = None
    volume: int | None = Field(default=None, ge=0)
    trading_value: int | None = Field(default=None, ge=0)
    session_type: str = "regular"
    as_of: datetime | None = None
    provider: str = "mock"
    data_key: str
    data_status: DataStatus = "ok"


class Candidate(StrictBaseModel):
    symbol: str
    name: str
    market: str = "KOSPI"
    categories: list[EventCategory] = Field(default_factory=list)
    score: float = Field(default=0, ge=0, le=10)
    main_reason: str
    source_ids: list[str] = Field(default_factory=list)
    price_snapshot: PriceSnapshot | None = None
    risk_flags: list[str] = Field(default_factory=list)
    observation_condition: str
    invalidation_condition: str

    @field_validator("source_ids")
    @classmethod
    def require_unique_sources(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class ReportContext(StrictBaseModel):
    report_date: str
    generated_at: datetime
    data_status: DataStatus
    events: list[MarketEvent]
    sources: list[Source]
    price_snapshots: list[PriceSnapshot]
    candidates: list[Candidate]
    market_context: dict[str, Any] = Field(default_factory=dict)
    missing_data: list[str] = Field(default_factory=list)


class VerificationResult(StrictBaseModel):
    status: VerificationStatus
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "pass"


class ReportBundle(StrictBaseModel):
    report_date: str
    generated_at: datetime
    markdown: str
    summary: dict[str, Any]
    verification: VerificationResult

    @model_validator(mode="after")
    def ensure_public_summary(self) -> ReportBundle:
        if "raw_response" in self.summary or "raw_prompt" in self.summary:
            raise ValueError("public summary cannot contain raw prompt or raw response")
        return self


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(KST_TIMEZONE))
    return parsed.astimezone(ZoneInfo(KST_TIMEZONE))


def model_dump_json_safe(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)

