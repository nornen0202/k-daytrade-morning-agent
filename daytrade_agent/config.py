from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from daytrade_agent.paths import project_root, resolve_from_root

KST_TIMEZONE = "Asia/Seoul"


@dataclass(frozen=True)
class AppConfig:
    root: Path
    content_dir: Path
    dist_dir: Path
    private_artifacts_dir: Path
    site_templates_dir: Path
    fixture_dir: Path
    timezone: str
    default_top_n: int
    disclaimer: str
    data_sources: dict[str, Any]
    category_weights: dict[str, float]
    risk_rules: dict[str, Any]

    @classmethod
    def load(cls, root: Path | None = None) -> AppConfig:
        load_dotenv()
        base = project_root(root)
        app = _load_yaml(base / "config" / "app.yml")
        return cls(
            root=base,
            content_dir=resolve_from_root(
                os.getenv("DAYTRADE_CONTENT_DIR") or app.get("content_dir", "content/reports"),
                base,
            ),
            dist_dir=resolve_from_root(
                os.getenv("DAYTRADE_DIST_DIR") or app.get("dist_dir", "dist"),
                base,
            ),
            private_artifacts_dir=resolve_from_root(
                os.getenv("DAYTRADE_PRIVATE_ARTIFACTS_DIR")
                or app.get("private_artifacts_dir", "private_artifacts"),
                base,
            ),
            site_templates_dir=base / "site_templates",
            fixture_dir=base / "tests" / "fixtures",
            timezone=str(app.get("timezone", KST_TIMEZONE)),
            default_top_n=int(app.get("default_top_n", 10)),
            disclaimer=str(
                app.get(
                    "disclaimer",
                    "이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.",
                )
            ),
            data_sources=_load_yaml(base / "config" / "data_sources.yml"),
            category_weights={
                str(key): float(value)
                for key, value in _load_yaml(base / "config" / "category_weights.yml").items()
            },
            risk_rules=_load_yaml(base / "config" / "risk_rules.yml"),
        )

    def env(self, name: str, default: str | None = None) -> str | None:
        value = os.getenv(name, default)
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def openai_model(self) -> str:
        default_model = (
            self.data_sources.get("openai", {}).get("default_model")
            if isinstance(self.data_sources.get("openai"), dict)
            else "gpt-5.5"
        )
        return self.env("OPENAI_REPORT_MODEL", str(default_model)) or "gpt-5.5"

    @property
    def debug_artifacts_enabled(self) -> bool:
        return (self.env("REPORT_DEBUG_ARTIFACTS", "false") or "false").lower() == "true"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data
