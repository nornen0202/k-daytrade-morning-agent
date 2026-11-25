from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import requests

from daytrade_agent.calendar.trading_calendar import premarket_cutoff
from daytrade_agent.config import AppConfig
from daytrade_agent.operations.git_store import PAGES_JOURNAL, GitError, GitStore
from daytrade_agent.operations.morning import (
    MANIFEST,
    Publication,
    json_bytes,
    latest_publication,
    main_tip,
    now_kst,
    report_digest,
    report_paths,
)
from daytrade_agent.render.site_builder import build_site

RECEIPT = "receipt.json"
INTENT_TTL = timedelta(minutes=30)
TERMINAL_FAILURE = {
    "deployment_failed", "deployment_perms_error", "deployment_content_failed",
    "deployment_cancelled", "deployment_lost",
}


@dataclass(frozen=True)
class Receipt:
    source_sha: str
    report_date: str
    sha256: str
    kind: str
    phase: str
    version: str
    attempt: int
    artifact_id: int
    artifact_digest: str
    run_id: str
    operation_id: str
    deployment_id: str | None = None
    status: str | None = None
    observed_at: str | None = None
    confirmed_before_cutoff: bool = False


@dataclass(frozen=True)
class Release:
    source_sha: str
    publication: Publication
    journal_tip: str | None
    previous: Receipt | None


class Pages:
    def __init__(self):
        self.root = (f"{os.environ['GITHUB_API_URL']}/repos/"
                     f"{os.environ['GITHUB_REPOSITORY']}")
        self.headers = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                        "Accept": "application/vnd.github+json"}

    def artifact_digest(self, artifact_id: int) -> str:
        response = requests.get(f"{self.root}/actions/artifacts/{artifact_id}",
                                headers=self.headers, timeout=15)
        response.raise_for_status()
        artifact = response.json()
        digest = artifact["digest"]
        if (artifact["expired"]
                or str(artifact["workflow_run"]["id"]) != os.environ["GITHUB_RUN_ID"]
                or not isinstance(digest, str) or not digest.startswith("sha256:")):
            raise RuntimeError("artifact is not eligible for this workflow run")
        return digest

    def status(self, receipt: Receipt) -> str:
        response = requests.get(
            f"{self.root}/pages/deployments/{receipt.deployment_id or receipt.version}",
            headers=self.headers, timeout=15,
        )
        if response.status_code == 404:
            return ""
        response.raise_for_status()
        return response.json()["status"]

    def oidc(self) -> str:
        header = {"Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"}
        response = requests.get(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"],
                                headers=header, timeout=15)
        response.raise_for_status()
        return response.json()["value"]

    def submit(self, receipt: Receipt, oidc: str) -> tuple[str | None, str | None]:
        response = requests.post(
            f"{self.root}/pages/deployments", headers=self.headers, timeout=30,
            json={"artifact_id": receipt.artifact_id, "pages_build_version": receipt.version,
                  "oidc_token": oidc},
        )
        if response.status_code in {400, 401, 403, 404, 422, 429}:
            return None, f"http_{response.status_code}"
        response.raise_for_status()
        data = response.json()
        return str(data.get("id") or receipt.version), None


def journal(git: GitStore) -> tuple[str | None, Receipt | None]:
    tip = git.remote_tip(PAGES_JOURNAL)
    if tip is None:
        return None, None
    data = git.path(tip, RECEIPT)
    if data is None:
        raise GitError("Pages journal is missing its receipt")
    return tip, Receipt(**json.loads(data))


def record(git: GitStore, base: str | None, receipt: Receipt) -> str:
    commit = git.commit(base, {RECEIPT: json_bytes(vars(receipt))},
                        f"Pages {receipt.phase} {receipt.report_date} {receipt.version}",
                        empty_tree=True)
    if not git.push(commit, PAGES_JOURNAL, base) and git.remote_tip(PAGES_JOURNAL) != commit:
        raise GitError("Pages journal changed concurrently")
    print(f"pages {receipt.phase} date={receipt.report_date} sha={receipt.source_sha} "
          f"sha256={receipt.sha256} version={receipt.version} artifact={receipt.artifact_id} "
          f"artifact_digest={receipt.artifact_digest} status={receipt.status} "
          f"deployment={receipt.deployment_id} "
          f"confirmed_before_cutoff={receipt.confirmed_before_cutoff}", flush=True)
    return commit


def _intent_expired(receipt: Receipt, current: datetime) -> bool:
    if receipt.phase != "intent" or receipt.deployment_id is not None:
        return False
    if current.date().isoformat() > receipt.report_date:
        return True
    if not receipt.observed_at:
        return False
    return current - datetime.fromisoformat(receipt.observed_at) >= INTENT_TTL


def reconcile(
    git: GitStore, pages: Pages, base: str, receipt: Receipt, *, polls: int,
) -> tuple[str, Receipt]:
    status = ""
    for poll in range(polls):
        status = pages.status(receipt)
        if status == "succeed" or status in TERMINAL_FAILURE:
            observed = now_kst()
            receipt = replace(
                receipt, phase="shipped" if status == "succeed" else "failed",
                status=status, observed_at=observed.isoformat(),
                confirmed_before_cutoff=(
                    receipt.kind == "research"
                    and status == "succeed"
                    and observed.date().isoformat() == receipt.report_date
                    and observed < premarket_cutoff(date.fromisoformat(receipt.report_date))
                ),
            )
            return record(git, base, receipt), receipt
        if poll + 1 < polls:
            time.sleep(5)
    observed = now_kst()
    if status == "" and _intent_expired(receipt, observed):
        expired = replace(
            receipt, phase="failed", status="intent_expired", observed_at=observed.isoformat(),
        )
        return record(git, base, expired), expired
    raise RuntimeError(f"Pages outcome unresolved for version {receipt.version}; "
                       "automatic resubmission is fenced")


def plan(git: GitStore, pages: Pages) -> Release | None:
    # Reconcile an earlier submission before allowing a newer Pages release.
    base, receipt = journal(git)
    if base and receipt and receipt.phase in {"intent", "submitted"}:
        base, receipt = reconcile(git, pages, base, receipt, polls=3)
    latest = latest_publication(git, main_tip(git))
    if latest is None:
        print("pages skipped: no selected report")
        return None
    sha, item = latest
    if receipt and (item.report_date < receipt.report_date
                    or (item.report_date == receipt.report_date and sha != receipt.source_sha)):
        raise RuntimeError("Pages target would reverse or replace the published date")
    if receipt and receipt.source_sha == sha and receipt.phase == "shipped":
        print(f"pages already shipped date={item.report_date} sha={sha} sha256={item.sha256}")
        return None
    return Release(sha, item, base, receipt)


def package(source: Path, output: Path, sha: str) -> None:
    git = GitStore(source)
    if git.output("rev-parse", "HEAD").decode().strip() != sha:
        raise RuntimeError("Pages checkout does not match the selected report")
    item = Publication(**json.loads((source / MANIFEST).read_bytes()))
    if report_digest({path: (source / path).read_bytes()
                      for path in report_paths(item.report_date)}) != item.sha256:
        raise RuntimeError("selected report differs from its manifest")
    config = replace(
        AppConfig.load(source), content_dir=source / "content/reports", dist_dir=output,
    )
    build_site(config)
    status = json.loads((output / "status.json").read_bytes())
    if status["latest_attempt"] != item.report_date:
        raise RuntimeError("Pages latest pointer differs from the selected report")
    (output / "publication.json").write_bytes(json_bytes({
        "source_sha": sha, **vars(item),
    }))


def deploy(git: GitStore, pages: Pages, target: str, artifact_id: int) -> None:
    # Take the journal snapshot before consulting main. A concurrent publisher can't use
    # a newer receipt to overwrite this snapshot while retaining a stale Pages target.
    latest = plan(git, pages)
    if latest is None or latest.source_sha != target:
        print(f"pages artifact skipped for non-pending source {target}")
        return
    sha, publication = latest.source_sha, latest.publication
    base, previous = latest.journal_tip, latest.previous
    attempt = previous.attempt + 1 if previous and previous.source_sha == sha else 1
    version = sha if attempt == 1 else hashlib.sha1(f"pages:{sha}:{attempt}".encode()).hexdigest()
    receipt = Receipt(
        source_sha=sha,
        report_date=publication.report_date,
        sha256=publication.sha256,
        kind=publication.kind,
        phase="intent",
        version=version,
        attempt=attempt,
        artifact_id=artifact_id,
        artifact_digest=pages.artifact_digest(artifact_id),
        run_id=os.environ["GITHUB_RUN_ID"],
        operation_id=uuid4().hex,
        observed_at=now_kst().isoformat(),
    )
    oidc = pages.oidc()
    base = record(git, base, receipt)
    try:
        deployment_id, rejection = pages.submit(receipt, oidc)
    except (requests.RequestException, ValueError):
        # A lost response is resolved by the unique Pages build version, never another POST.
        _, recovered = reconcile(git, pages, base, receipt, polls=36)
        if recovered.phase != "shipped":
            raise RuntimeError("Pages deployment failed after a lost response") from None
        return
    if rejection:
        record(git, base, replace(
            receipt, phase="failed", status=rejection, observed_at=now_kst().isoformat(),
        ))
        raise RuntimeError(f"Pages rejected the request ({rejection})")
    receipt = replace(receipt, phase="submitted", deployment_id=deployment_id)
    base = record(git, base, receipt)
    _, final = reconcile(git, pages, base, receipt, polls=36)
    if final.phase != "shipped":
        raise RuntimeError(f"Pages deployment failed ({final.status})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Package and deploy the selected Pages release")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("plan")
    pack = subs.add_parser("package")
    pack.add_argument("--source", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--sha", required=True)
    ship = subs.add_parser("deploy")
    ship.add_argument("--sha", required=True)
    ship.add_argument("--artifact-id", type=int, required=True)
    args = parser.parse_args()
    if args.command == "package":
        package(args.source.resolve(), args.output.resolve(), args.sha)
    elif args.command == "plan":
        selected = plan(GitStore(Path.cwd()), Pages())
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            print(f"source_sha={selected.source_sha if selected else ''}", file=output)
    else:
        deploy(GitStore(Path.cwd()), Pages(), args.sha, args.artifact_id)


if __name__ == "__main__":
    main()
