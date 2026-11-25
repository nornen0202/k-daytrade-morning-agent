from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from daytrade_agent.calendar.trading_calendar import (
    MORNING_START,
    SEOUL,
    premarket_cutoff,
    trading_status,
)
from daytrade_agent.config import AppConfig
from daytrade_agent.operations.git_store import MAIN, SHA, GitError, GitStore

PROTOCOL_FILE = ".github/daytrade-publication-v1"
PROTOCOL = b"morning-publication-v1"
MANIFEST = "content/publication/morning.json"
REPORT_FILES = ("report.md", "summary.json", "verification.json")


def now_kst() -> datetime:
    return datetime.now(SEOUL)


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def report_paths(day: str) -> tuple[str, ...]:
    return tuple(f"content/reports/{day}/{name}" for name in REPORT_FILES)


def report_digest(files: dict[str, bytes]) -> str:
    # The path and each file's fixed-length hash preserve file boundaries.
    manifest = {path: hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
                for path, data in files.items()}
    return hashlib.sha256(json_bytes(manifest)).hexdigest()


@dataclass(frozen=True)
class Publication:
    report_date: str
    kind: str
    sha256: str
    selected_at: str
    trigger: str


def main_tip(git: GitStore) -> str:
    tip = git.remote_tip(MAIN)
    marker = git.path(tip, PROTOCOL_FILE) if tip else None
    if tip is None or marker is None or marker.strip() != PROTOCOL:
        raise GitError("origin/main has not enabled the morning publication protocol")
    return tip


def latest_publication(git: GitStore, tip: str) -> tuple[str, Publication] | None:
    data = git.path(tip, MANIFEST)
    if data is None:
        return None
    item = Publication(**json.loads(data))
    if (date.fromisoformat(item.report_date).isoformat() != item.report_date
            or item.kind not in {"research", "notice"}):
        raise GitError("invalid publication manifest")
    commit = git.output(
        "log", "--first-parent", "-1", "--format=%H", tip, "--", MANIFEST,
    ).decode().strip()
    if not SHA.fullmatch(commit):
        raise GitError("cannot resolve the publication commit")
    return commit, item


def staged_report(config: AppConfig, day: str, trigger: str, market: str) -> Path | None:
    from daytrade_agent.cli import run_command, verify_command
    from daytrade_agent.render.site_builder import apply_publication_gate
    from daytrade_agent.storage.report_store import load_report

    # Completed directories are durable across process restarts. A late invocation uses a
    # separate slot and can never reuse an unpublished premarket capture.
    late = market == "open" and now_kst() >= premarket_cutoff(date.fromisoformat(day))
    staging = config.private_artifacts_dir / "morning" / trigger / day
    staging.mkdir(parents=True, exist_ok=True)
    slot = staging / ("late" if late else "ready")
    if not slot.exists():
        with TemporaryDirectory(dir=staging) as temp:
            work = replace(config, content_dir=Path(temp))
            begin = now_kst()
            print(f"morning start trigger={trigger} market={market} at={begin.isoformat()}",
                  flush=True)
            if run_command(work, day, dry_run=False) or verify_command(work, day) not in (0, 1):
                raise RuntimeError("report staging or verification did not complete")
            candidate = load_report(work.content_dir, day)
            apply_publication_gate(candidate, now_kst())
            if market == "open" and not candidate["current"] and not late:
                # Leave the premarket slot open for a retry, or create the standard late
                # notice below if collection crossed the cutoff.
                if now_kst() >= premarket_cutoff(date.fromisoformat(day)):
                    return staged_report(config, day, trigger, market)
                return None
            try:
                (Path(temp) / day).rename(slot)
            except OSError:
                if not slot.is_dir():
                    raise
    return slot


def collect(config: AppConfig, trigger: str, requested_date: str | None) -> None:
    start = now_kst()
    day = start.date().isoformat()
    if requested_date and requested_date != day:
        raise ValueError("live collection requires the current KST date")
    if start.time() < MORNING_START or start.weekday() >= 5:
        print(f"morning skipped trigger={trigger} at={start.isoformat()}")
        return
    git = GitStore(config.root)
    if start >= premarket_cutoff(start.date()):
        try:
            latest = latest_publication(git, main_tip(git))
        except GitError:
            latest = None
        if _already_selected(latest, day):
            return
    market = trading_status(start.date())
    slot = staged_report(config, day, trigger, market)
    if slot is None:
        print(f"morning deferred trigger={trigger} day={day} reason=no_verified_research")
        return
    publish(config, git, day, trigger, market, slot)


def _already_selected(latest: tuple[str, Publication] | None, day: str) -> bool:
    if latest is None or latest[1].report_date < day:
        return False
    commit, item = latest
    print(f"morning already selected date={item.report_date} sha={commit} sha256={item.sha256}")
    return True


def publish(
    config: AppConfig, git: GitStore, day: str, trigger: str, market: str, slot: Path,
) -> None:
    from daytrade_agent.render.site_builder import apply_publication_gate
    from daytrade_agent.storage.report_store import load_report

    for _ in range(4):
        tip = main_tip(git)
        latest = latest_publication(git, tip)
        if _already_selected(latest, day):
            return
        reports = git.output("ls-tree", "-d", tip, "--", "content/reports")
        existing = git.output(
            "ls-tree", "-d", "--name-only", f"{tip}:content/reports",
        ).decode().split() if reports else []
        if any(name >= day for name in existing if len(name) == len(day)):
            print(f"morning preserved existing report at or after {day}")
            return
        selected = now_kst()
        if selected.date().isoformat() != day:
            print(f"morning expired selection day={day} at={selected.isoformat()}")
            return
        kind = "research" if market == "open" and slot.name == "ready" else "notice"
        if kind == "research" and selected >= premarket_cutoff(selected.date()):
            late_slot = staged_report(config, day, trigger, market)
            if late_slot is None:
                raise RuntimeError("late notice staging did not complete")
            slot = late_slot
            continue
        stored = load_report(slot.parent, slot.name)
        stored["report_date"] = day
        apply_publication_gate(stored, selected)
        if (stored["summary"].get("run_mode") != "live"
                or (kind == "research") != stored["current"]):
            raise ValueError("staged report failed publication verification")
        files = {path: (slot / Path(path).name).read_bytes() for path in report_paths(day)}
        item = Publication(day, kind, report_digest(files), selected.isoformat(), trigger)
        files[MANIFEST] = json_bytes(vars(item))
        proposed = git.commit(tip, files, f"chore: publish morning report {day}")
        if kind == "research" and now_kst() >= premarket_cutoff(selected.date()):
            continue
        if git.push(proposed, MAIN, tip):
            print(f"morning selected date={day} kind={kind} sha={proposed} sha256={item.sha256}")
            return
        # Both a competing push and a lost push acknowledgement are resolved by rereading main.
    tip = main_tip(git)
    latest = latest_publication(git, tip)
    if latest and latest[1].report_date >= day:
        print(f"morning reconciled date={latest[1].report_date} sha={latest[0]} "
              f"sha256={latest[1].sha256}")
        return
    raise GitError("morning report remains staged after unsuccessful compare-and-swap")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and atomically select the morning report")
    parser.add_argument("--trigger", choices=["windows", "github"], required=True)
    parser.add_argument("--date")
    args = parser.parse_args()
    collect(AppConfig.load(Path.cwd()), args.trigger, args.date)


if __name__ == "__main__":
    main()
