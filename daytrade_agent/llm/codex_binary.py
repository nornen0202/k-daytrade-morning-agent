from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def resolve_codex_binary(codex_binary: str | None = None) -> str | None:
    requested_candidates = [
        _normalize_explicit_binary(codex_binary),
        _normalize_explicit_binary(os.getenv("CODEX_BINARY")),
    ]
    for candidate in requested_candidates:
        if candidate and _is_usable_codex_binary(candidate):
            return candidate

    discovered: list[str] = []
    path_binary = shutil.which("codex")
    if path_binary:
        discovered.append(path_binary)
    discovered.extend(str(candidate) for candidate in _windows_codex_candidates())

    first_existing: str | None = None
    for candidate in _dedupe(discovered):
        path = Path(candidate)
        if not path.is_file():
            continue
        if first_existing is None:
            first_existing = str(path)
        if _is_usable_codex_binary(str(path)):
            return str(path)

    for candidate in requested_candidates:
        if candidate:
            return candidate
    return first_existing


def codex_binary_error_message(codex_binary: str | None = None) -> str:
    requested = codex_binary or os.getenv("CODEX_BINARY") or "codex"
    message = (
        f"Could not find a usable Codex binary '{requested}'. Set CODEX_BINARY or install "
        "Codex for the self-hosted runner service account."
    )
    discovered = [str(path) for path in _windows_codex_candidates() if path.is_file()]
    if discovered:
        message += f" Detected candidate: {discovered[0]}"
    return message


def _normalize_explicit_binary(value: str | None) -> str | None:
    if not value:
        return None
    expanded = str(Path(value).expanduser())
    has_separator = any(sep and sep in expanded for sep in (os.path.sep, os.path.altsep))
    if has_separator:
        return expanded if Path(expanded).is_file() else None
    return shutil.which(expanded)


def _windows_codex_candidates() -> list[Path]:
    if os.name != "nt":
        return []
    home = Path.home()
    candidates = sorted(
        home.glob(r".vscode/extensions/openai.chatgpt-*/bin/windows-x86_64/codex.exe"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    candidates.extend(
        [
            home / ".codex" / ".sandbox-bin" / "codex.exe",
            home / ".codex" / "bin" / "codex.exe",
            home / "AppData" / "Local" / "Programs" / "Codex" / "codex.exe",
        ]
    )
    return candidates


def _is_usable_codex_binary(binary: str) -> bool:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _dedupe(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        normalized = os.path.normcase(os.path.normpath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique

