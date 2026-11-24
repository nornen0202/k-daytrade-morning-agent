from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from daytrade_agent.operations.git_store import MAIN, PAGES_JOURNAL, GitStore
from daytrade_agent.operations.morning import latest_publication, main_tip
from daytrade_agent.operations.pages import journal

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-04-27"
START = f"{DAY}T08:45:00+09:00"
AFTER = f"{DAY}T09:00:00+09:00"
ARTIFACT_DIGEST = "sha256:" + hashlib.sha256(b"isolated Pages artifact").hexdigest()


def git(cwd, *args):
    return GitStore(cwd).output(*args).decode().strip()


@pytest.fixture
def sandbox(tmp_path):
    remote = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    git(tmp_path, "init", "--bare", str(remote))
    git(seed, "init", "-b", "main")
    for name in ("config", "site_templates", "prompts"):
        shutil.copytree(ROOT / name, seed / name)
    (seed / ".github").mkdir()
    shutil.copy(ROOT / ".github/daytrade-publication-v1", seed / ".github")
    git(seed, "add", ".")
    git(seed, "-c", "user.name=Test", "-c", "user.email=test@example.test",
        "commit", "-m", "isolated project")
    git(seed, "push", str(remote), "main")
    clones = []
    for name in ("windows", "github"):
        target = tmp_path / name
        git(tmp_path, "clone", "-b", "main", str(remote), str(target))
        clones.append(target)
    return (*clones, remote)


def run(sandbox, entry, *args, client=0, clock=START, check=True, **overrides):
    folder = sandbox[client]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1",
           "REPORT_LLM_PROVIDER": "template", "TEST_MORNING_CLOCK": clock,
           "TEST_MORNING_ORIGIN": git(folder, "remote", "get-url", "origin"),
           "DAYTRADE_PRIVATE_ARTIFACTS_DIR": str(folder / "private_artifacts"), **overrides}
    response = subprocess.run(
        [sys.executable, "-c", "from tests.morning_process import run; run()", entry, *args],
        cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8", timeout=70,
        check=False,
    )
    if check:
        assert response.returncode == 0, response.stdout + response.stderr
    print(response.stdout, end="")
    return response


def selected(sandbox):
    store = GitStore(sandbox[0])
    return latest_publication(store, main_tip(store))


def collect(sandbox, trigger, **kwargs):
    return run(sandbox, "morning", "--trigger", trigger, client=int(trigger == "github"), **kwargs)


@pytest.mark.parametrize("first", ("windows", "github"))
def test_first_verified_research_is_retained_by_late_other_process(sandbox, first):
    output = collect(sandbox, first).stdout
    assert f"simulated upstream collection at {START}" in output
    before = selected(sandbox)
    assert before[1].kind == "research"
    second = "github" if first == "windows" else "windows"
    assert "simulated upstream" not in collect(sandbox, second, clock=AFTER).stdout
    assert selected(sandbox) == before
    assert git(sandbox[2], "rev-list", "--count", MAIN) == "2"


def test_two_processes_race_for_one_git_result_then_next_day_is_monotonic(sandbox, tmp_path):
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(collect, sandbox, origin, TEST_MORNING_RACE=str(barrier))
                for origin in ("windows", "github")]
        outputs = [job.result().stdout for job in jobs]
    assert all("simulated upstream" in output for output in outputs)
    assert sum("morning selected" in output for output in outputs) == 1
    assert len(list(barrier.iterdir())) == 2
    older = selected(sandbox)
    tomorrow = "2026-04-28T08:45:00+09:00"
    collect(sandbox, "windows", clock=tomorrow)
    newer = selected(sandbox)
    collect(sandbox, "github", clock=AFTER)
    assert selected(sandbox) == newer and newer[1].report_date > older[1].report_date
    assert git(sandbox[2], "rev-list", "--count", MAIN) == "3"


@pytest.mark.parametrize(("stamp", "cross", "status", "had_collection"), [
    ("2026-04-25T08:45:00+09:00", "", None, False),  # Saturday
    ("2027-05-03T08:45:00+09:00", "", "closed", False),  # Reviewed XKRX holiday
    ("2026-04-27T08:59:59+09:00", "1", "missed", True),
    (AFTER, "", "missed", False),
])
def test_calendar_cutoff_and_late_first(sandbox, stamp, cross, status, had_collection):
    output = collect(sandbox, "windows", clock=stamp, TEST_MORNING_CROSS_CUTOFF=cross).stdout
    assert ("simulated upstream" in output) == had_collection
    picked = selected(sandbox)
    if status is None:
        assert picked is None
        return
    sha, report = picked
    summary_path = f"content/reports/{report.report_date}/summary.json"
    summary = json.loads(git(sandbox[2], "show", f"{sha}:{summary_path}"))
    assert report.kind == "notice"
    assert summary["market_context"]["market_status"] == status
    assert summary["candidates"] == []
    retry_time = AFTER if status == "missed" else stamp
    assert "simulated upstream" not in collect(sandbox, "github", clock=retry_time).stdout
    assert selected(sandbox) == picked


def test_precommit_failure_recovers_staged_result_and_lost_git_ack(sandbox):
    failed = collect(sandbox, "windows", check=False, TEST_MORNING_FAIL_PUSH="1")
    assert failed.returncode != 0 and selected(sandbox) is None
    recovered = collect(sandbox, "windows", TEST_MORNING_LOSE_GIT_ACK="1")
    assert "simulated upstream" not in recovered.stdout
    assert "morning already selected" in recovered.stdout
    assert selected(sandbox)[1].kind == "research"
    assert git(sandbox[2], "rev-list", "--count", MAIN) == "2"


def test_windows_starts_collection_even_when_git_is_unreachable(sandbox, tmp_path):
    git(sandbox[0], "remote", "set-url", "origin", str(tmp_path / "unreachable.git"))
    failed = collect(sandbox, "windows", check=False)
    assert failed.returncode != 0
    assert f"simulated upstream collection at {START}" in failed.stdout
    assert "cannot read origin" in failed.stderr
    assert git(sandbox[2], "rev-list", "--count", MAIN) == "1"


@pytest.fixture
def provider():
    state = {"calls": [], "statuses": {}, "mode": "success"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path == "/oidc":
                self.send(200, {"value": "fixture"})
            elif "/actions/artifacts/" in self.path:
                self.send(200, {"digest": ARTIFACT_DIGEST, "expired": False,
                                "workflow_run": {"id": 123}})
            else:
                version = self.path.rsplit("/", 1)[-1]
                self.send(200, {"status": state["statuses"].get(version, "")})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            version = payload["pages_build_version"]
            state["calls"].append(version)
            if state["mode"] == "unresolved":
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            state["statuses"][version] = (
                "deployment_failed" if state["mode"] == "terminal_failure" else "succeed"
            )
            if state["mode"] == "lose_response":
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            self.send(200, {"id": version})

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        listener = Thread(target=server.serve_forever, daemon=True)
        listener.start()
        url = f"http://127.0.0.1:{server.server_port}"
        env = {"GITHUB_API_URL": url, "GITHUB_REPOSITORY": "isolated/report", "GH_TOKEN": "fixture",
               "GITHUB_RUN_ID": "123", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "fixture",
               "ACTIONS_ID_TOKEN_REQUEST_URL": url + "/oidc"}
        yield state, env
        server.shutdown()
        listener.join()


@pytest.mark.parametrize("loss", ("lose_response", "crash", "unresolved"))
def test_pages_ack_reconciles_by_version_without_a_second_post(sandbox, provider, tmp_path, loss):
    collect(sandbox, "windows")
    sha, publication = selected(sandbox)
    source = tmp_path / "source"
    git(tmp_path, "clone", "-b", "main", str(sandbox[2]), str(source))
    dist = tmp_path / "dist"
    run(sandbox, "pages", "package", "--source", str(source), "--output", str(dist), "--sha", sha)
    status = json.loads((dist / "status.json").read_bytes())
    assert status["latest_attempt"] == publication.report_date
    assert json.loads((dist / "publication.json").read_bytes())["sha256"] == publication.sha256
    state, env = provider
    state["mode"] = loss
    command = ("deploy", "--sha", sha, "--artifact-id", "17")
    result = run(sandbox, "pages", *command, **env, check=False,
                 TEST_MORNING_CRASH_AFTER_POST="1" if loss == "crash" else "")
    assert result.returncode == {"lose_response": 0, "crash": 29, "unresolved": 1}[loss]
    if loss == "unresolved":
        blocked = run(sandbox, "pages", *command, **env, client=1, check=False)
        assert blocked.returncode == 1
        assert "automatic resubmission is fenced" in blocked.stderr
        state["statuses"][sha] = "succeed"
    run(sandbox, "pages", *command, **env, client=1)
    assert state["calls"] == [sha]
    receipt = journal(GitStore(sandbox[1]))[1]
    assert (receipt.phase, receipt.source_sha, receipt.sha256, receipt.artifact_digest) == (
        "shipped", sha, publication.sha256, ARTIFACT_DIGEST,
    )


def test_pages_terminal_failure_retries_and_previous_date_cannot_follow_newer_release(
    sandbox, provider,
):
    state, env = provider
    collect(sandbox, "github")
    first, _ = selected(sandbox)
    state["mode"] = "terminal_failure"
    attempt = ("deploy", "--sha", first, "--artifact-id", "17")
    assert run(sandbox, "pages", *attempt, **env, check=False).returncode == 1
    origin = GitStore(sandbox[0])
    assert journal(origin)[1].phase == "failed"
    state["mode"] = "success"
    run(sandbox, "pages", *attempt, **env, client=1)
    retry = journal(origin)[1]
    assert retry.phase == "shipped" and retry.attempt == 2
    assert retry.source_sha == first and retry.version != first
    tomorrow = "2026-04-28T08:45:00+09:00"
    collect(sandbox, "windows", clock=tomorrow)
    latest, _ = selected(sandbox)
    run(sandbox, "pages", "deploy", "--sha", latest, "--artifact-id", "18", **env, clock=tomorrow)
    run(sandbox, "pages", *attempt, **env, client=1)
    assert state["calls"] == [first, retry.version, latest]
    assert journal(origin)[1].source_sha == latest
    assert git(sandbox[2], "rev-list", "--count", PAGES_JOURNAL) == "9"


def test_two_pages_processes_can_only_send_one_publication_request(sandbox, provider, tmp_path):
    collect(sandbox, "windows")
    sha, publication = selected(sandbox)
    state, env = provider
    barrier = tmp_path / "pages_barrier"
    barrier.mkdir()
    command = ("pages", "deploy", "--sha", sha, "--artifact-id", "17")
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(run, sandbox, *command, client=client, check=False,
                                TEST_PAGES_RACE=str(barrier), **env)
                for client in (0, 1)]
    assert sorted(job.result().returncode for job in jobs) == [0, 1]
    assert len(list(barrier.iterdir())) == 2
    assert state["calls"] == [sha]
    receipt = journal(GitStore(sandbox[0]))[1]
    assert (receipt.phase, receipt.sha256) == ("shipped", publication.sha256)
