from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

MAIN = "refs/heads/main"
PAGES_JOURNAL = "refs/heads/daytrade-pages-receipts"
SHA = re.compile(r"[0-9a-f]{40}")


class GitError(RuntimeError):
    pass


class GitStore:
    def __init__(self, root: Path):
        self.root = root

    def run(self, *args: str, data: bytes | None = None, index: Path | None = None):
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        try:
            return subprocess.run(
                ["git", *args], cwd=self.root, env=env, input=data, capture_output=True,
                timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            raise GitError(f"git {args[0]} timed out") from None

    def output(self, *args: str, data: bytes | None = None, index: Path | None = None) -> bytes:
        result = self.run(*args, data=data, index=index)
        if result.returncode:
            raise GitError(f"git {args[0]} failed ({result.returncode})")
        return result.stdout

    def remote_tip(self, ref: str) -> str | None:
        probe = self.run("ls-remote", "--exit-code", "--refs", "origin", ref)
        if probe.returncode == 2:
            return None
        if probe.returncode:
            raise GitError(f"cannot read origin {ref} ({probe.returncode})")
        observed = probe.stdout.decode().split()[0]
        if not SHA.fullmatch(observed):
            raise GitError(f"unexpected origin ref {ref}")
        # Fetch by object ID so concurrent fetches cannot change the snapshot being read.
        if self.run("cat-file", "-e", f"{observed}^{{commit}}").returncode:
            self.output("fetch", "--no-tags", "--no-write-fetch-head", "origin", observed)
        return observed

    def path(self, commit: str, path: str) -> bytes | None:
        if self.output("ls-tree", commit, "--", path):
            return self.output("show", f"{commit}:{path}")
        return None

    def commit(
        self, parent: str | None, files: dict[str, bytes], message: str,
        *, empty_tree: bool = False,
    ) -> str:
        with TemporaryDirectory() as temp:
            index = Path(temp) / "index"
            if parent and not empty_tree:
                self.output("read-tree", parent, index=index)
            for path, data in sorted(files.items()):
                blob = self.output("hash-object", "-w", "--stdin", data=data).decode().strip()
                self.output("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}",
                            index=index)
            tree = self.output("write-tree", index=index).decode().strip()
        identity = ("-c", "user.name=Daytrade Publisher", "-c",
                    "user.email=41898282+github-actions[bot]@users.noreply.github.com")
        parents = ["-p", parent] if parent else []
        return self.output(*identity, "commit-tree", tree, *parents, "-m", message).decode().strip()

    def push(self, commit: str, ref: str, parent: str | None) -> bool:
        try:
            return self.run(
                "push", "--porcelain", f"--force-with-lease={ref}:{parent or ''}", "origin",
                f"{commit}:{ref}",
            ).returncode == 0
        except GitError:
            # A timeout can occur after the remote advanced. Callers reconcile the remote tip.
            return False
