"""One private Codex generation check, with no public report or Pages writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from daytrade_agent.cli import _build_context, _collect_all
from daytrade_agent.config import AppConfig
from daytrade_agent.llm import report_writer
from daytrade_agent.llm.codex_app_server import CodexAppServerSession
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.normalizers.event_schema import ReportContext


def main() -> int:
    config = AppConfig.load()
    parser = argparse.ArgumentParser()
    parser.add_argument("--reverify", type=Path)
    args = parser.parse_args()
    if args.reverify:
        folder = args.reverify.resolve()
        if not folder.is_relative_to(config.private_artifacts_dir.resolve()):
            parser.error("Replay input must be in this project's private artifacts")
        context = ReportContext.model_validate_json((folder / "context.json").read_text("utf-8"))
        markdown = (folder / "draft.md").read_text("utf-8")
        verification = verify_report(context, markdown)
        result = {
            "mode": "offline_reverification", "model_invocations": 0,
            "output_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
            "verification": verification.model_dump(),
        }
        (folder / "reverification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False))
        return 1 if verification.status == "fail" else 0
    stamp = datetime.now(ZoneInfo("Asia/Seoul"))
    folder = config.private_artifacts_dir / "codex-model-probe" / stamp.strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=False)
    config.data_sources["news"]["provider_priority"] = ["naver"]
    context = _build_context(
        config, stamp.date().isoformat(), stamp,
        _collect_all(config, stamp.date().isoformat(), stamp, dry_run=False),
    )
    # Keep the existing context contracts while bounding this single model invocation.
    selected = []
    for category in ("political_theme", "corporate_disclosure", "global_issue", "theme_surge"):
        selected.extend([event for event in context.events if event.category == category][:1])
    context.events = selected
    ids = {event.source_id for event in selected}
    context.sources = [source for source in context.sources if source.source_id in ids]
    context.candidates = []
    context.price_snapshots = []
    context.market_context = {"run_mode": "private_model_probe"}
    context.missing_data.append("비공개 모델 연결 점검. 장전 발행이나 오늘의 연구 결과가 아님.")
    (folder / "context.json").write_text(context.model_dump_json(indent=2), encoding="utf-8")
    receipt = {
        "purpose": "private_model_probe", "public_report_written": False,
        "started_at": stamp.isoformat(), "selected_model": config.codex_model,
        "effort": config.env("CODEX_REASONING_EFFORT", "medium"),
        "timeout_seconds": float(config.env("CODEX_REQUEST_TIMEOUT", "180")),
        "invocation_count": 0, "generation_completed": False,
        "event_count": len(context.events), "source_times": [
            event.published_at.isoformat() for event in context.events if event.published_at
        ], "api_billed_cost": None,
    }
    original_session = report_writer.CodexAppServerSession

    class ProbeSession(CodexAppServerSession):
        def request(self, method, params=None):
            result = super().request(method, params)
            if method == "thread/start":
                receipt["server_model"] = (
                    result.get("model") or result.get("thread", {}).get("model")
                )
            return result

        def invoke(self, **kwargs):
            receipt["invocation_count"] += 1
            receipt["requested_model"] = kwargs["model"]
            self.start()
            account = self.account_read().get("account") or {}
            receipt["account_type"] = account.get("type")
            if receipt["account_type"] != "chatgpt":
                raise RuntimeError("This probe requires existing ChatGPT login")
            models = self.model_list().get("data", [])
            receipt["model_available"] = any(
                kwargs["model"] in {item.get("model"), item.get("id")}
                for item in models if isinstance(item, dict)
            )
            if not receipt["model_available"]:
                raise RuntimeError("Requested model is unavailable")
            result = super().invoke(**kwargs)
            receipt["generation_completed"] = True
            receipt["token_usage"] = [
                item.get("params", {}).get("tokenUsage")
                for item in result.notifications
                if item.get("method") == "thread/tokenUsage/updated"
            ][-1:]
            receipt["completion_events"] = sum(
                item.get("method") == "turn/completed" for item in result.notifications
            )
            return result

    started = time.monotonic()
    report_writer.CodexAppServerSession = ProbeSession
    try:
        # This is the production writer, including its normal fallback behavior.
        markdown = report_writer.write_report_markdown(config, context, dry_run=False)
    finally:
        report_writer.CodexAppServerSession = original_session
    verification = verify_report(context, markdown)
    receipt.update({
        "writer_provider": context.market_context.get("writer_provider"),
        "writer_model": context.market_context.get("writer_model"),
        "fallback": context.market_context.get("writer_provider") != "codex",
        "verification": verification.model_dump(mode="json"),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "output_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
    })
    (folder / "draft.md").write_text(markdown, encoding="utf-8")
    (folder / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False))
    print(f"Private receipt: {folder}")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write("## Private Codex probe\n\n")
            handle.write(f"- Model: {receipt.get('writer_model')}\n")
            handle.write(f"- Completed: {receipt['generation_completed']}\n")
            handle.write(f"- Fallback: {receipt['fallback']}\n")
            handle.write(f"- Verification: {verification.status}\n")
            handle.write("- Public report written: false\n")
    return 1 if receipt["fallback"] or verification.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
