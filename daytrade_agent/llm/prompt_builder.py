from __future__ import annotations

import json
from pathlib import Path

from daytrade_agent.normalizers.event_schema import ReportContext, model_dump_json_safe


def build_prompt(context: ReportContext, prompt_path: Path) -> str:
    instructions = prompt_path.read_text(encoding="utf-8")
    facts_json = json.dumps(model_dump_json_safe(context), ensure_ascii=False, indent=2)
    return (
        f"{instructions}\n\n"
        "## Facts JSON\n\n"
        "```json\n"
        f"{facts_json}\n"
        "```\n"
    )


def build_prompt_payload(context: ReportContext) -> dict[str, object]:
    return model_dump_json_safe(context)

