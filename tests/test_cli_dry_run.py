import subprocess
import sys
from pathlib import Path


def test_cli_dry_run_and_build_site(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = _test_env(tmp_path)

    run = subprocess.run(
        [sys.executable, "-m", "daytrade_agent.cli", "run", "--dry-run", "--date", "2026-04-27"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stderr

    build = subprocess.run(
        [sys.executable, "-m", "daytrade_agent.cli", "build-site"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    assert (tmp_path / "dist" / "index.html").exists()
    assert (tmp_path / "dist" / "reports" / "2026-04-27" / "index.html").exists()


def test_cli_weekend_creates_market_closed_note(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = _test_env(tmp_path)

    run = subprocess.run(
        [sys.executable, "-m", "daytrade_agent.cli", "run", "--dry-run", "--date", "2026-04-26"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    report = tmp_path / "content" / "reports" / "2026-04-26" / "report.md"
    assert report.exists()
    assert "Market Closed Note" in report.read_text(encoding="utf-8")


def _test_env(tmp_path):
    import os

    env = os.environ.copy()
    env["DAYTRADE_CONTENT_DIR"] = str(tmp_path / "content" / "reports")
    env["DAYTRADE_DIST_DIR"] = str(tmp_path / "dist")
    env["DAYTRADE_PRIVATE_ARTIFACTS_DIR"] = str(tmp_path / "private_artifacts")
    return env
