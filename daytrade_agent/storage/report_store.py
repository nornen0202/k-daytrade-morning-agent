from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from daytrade_agent.normalizers.event_schema import VerificationResult


def save_report(
    content_dir: Path,
    report_date: str,
    markdown: str,
    summary: dict[str, Any],
    verification: VerificationResult,
) -> Path:
    _check_public_boundary(markdown, summary)
    destination = content_dir / report_date
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.md").write_text(markdown, encoding="utf-8")
    _write_json(destination / "summary.json", summary)
    _write_json(destination / "verification.json", verification.model_dump(mode="json"))
    return destination


def load_report(content_dir: Path, report_date: str) -> dict[str, Any]:
    directory = content_dir / report_date
    return {
        "report_date": report_date,
        "markdown": (directory / "report.md").read_text(encoding="utf-8"),
        "summary": _read_json(directory / "summary.json"),
        "verification": _read_json(directory / "verification.json"),
        "path": directory,
    }


def discover_reports(content_dir: Path) -> list[dict[str, Any]]:
    if not content_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    for directory in content_dir.iterdir():
        if not directory.is_dir():
            continue
        summary_path = directory / "summary.json"
        verification_path = directory / "verification.json"
        markdown_path = directory / "report.md"
        if (
            not summary_path.exists()
            or not verification_path.exists()
            or not markdown_path.exists()
        ):
            continue
        reports.append(
            {
                "report_date": directory.name,
                "summary": _read_json(summary_path),
                "verification": _read_json(verification_path),
                "markdown": markdown_path.read_text(encoding="utf-8"),
            }
        )
    return sorted(reports, key=lambda item: item["report_date"], reverse=True)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _check_public_boundary(markdown: str, summary: dict[str, Any]) -> None:
    text = markdown + json.dumps(summary, ensure_ascii=False)
    for key, value in os.environ.items():
        if (any(marker in key.upper() for marker in ("API_KEY", "APP_KEY", "SECRET", "TOKEN"))
                and len(value) >= 8 and value in text):
            raise ValueError("public artifact contains a configured credential")

    forbidden = {"raw_response", "raw_prompt", "access_token", "refresh_token", "authorization",
                 "account_number", "holdings", "api_key", "app_secret"}

    def check(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden.intersection(key.lower() for key in value):
                raise ValueError("public artifact contains private payload fields")
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(summary)
