"""Drive the production CLIs with a fixed clock and synthetic upstream inputs."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from daytrade_agent import cli
from daytrade_agent.collectors.mock import collect_mock
from daytrade_agent.operations import morning, pages
from daytrade_agent.operations.git_store import MAIN, PAGES_JOURNAL, GitStore

_ROOT = Path(__file__).resolve().parents[1]


def run() -> None:
    args = sys.argv
    entry = args.pop(1)
    moment = datetime.fromisoformat(os.environ["TEST_MORNING_CLOCK"])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz)

    def capture(config, day, started, *, dry_run):
        nonlocal moment
        print(f"simulated upstream collection at {started.isoformat()}", flush=True)
        if os.getenv("TEST_MORNING_CROSS_CUTOFF"):
            moment += timedelta(seconds=1)
        result = collect_mock(replace(config, fixture_dir=_ROOT / "tests/fixtures"), day, started)
        for index, source in enumerate(result.sources):
            source.source_name = "Synthetic Publisher"
            source.source_url = f"https://synthetic.example.test/article-{index}"
        return [result]

    git = GitStore(Path.cwd())
    origin = git.output("remote", "get-url", "origin").decode().strip()
    if origin != os.environ["TEST_MORNING_ORIGIN"]:
        raise RuntimeError("these tests require the isolated Git remote")
    original_push = GitStore.push

    def push(self, commit, ref, parent):
        barrier = os.getenv("TEST_MORNING_RACE" if ref == MAIN else "TEST_PAGES_RACE")
        if barrier and ref in {MAIN, PAGES_JOURNAL}:
            root = Path(barrier)
            (root / str(os.getpid())).touch()
            for _ in range(300):
                if len(list(root.iterdir())) >= 2:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("the second publication process did not reach the CAS")
        if ref == MAIN and os.getenv("TEST_MORNING_FAIL_PUSH"):
            return False
        applied = original_push(self, commit, ref, parent)
        return applied and not (ref == MAIN and os.getenv("TEST_MORNING_LOSE_GIT_ACK"))

    GitStore.push = push
    cli.datetime = Clock
    cli._collect_all = capture
    morning.now_kst = lambda: Clock.now(morning.SEOUL)
    pages.now_kst = morning.now_kst
    if entry == "pages":
        pages.time = SimpleNamespace(sleep=lambda _: None)
        if os.getenv("TEST_MORNING_CRASH_AFTER_POST"):
            original_record = pages.record

            def record(git, base, receipt):
                if receipt.phase == "submitted":
                    os._exit(29)
                return original_record(git, base, receipt)

            pages.record = record
        pages.main()
    else:
        morning.main()
