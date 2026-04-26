from __future__ import annotations

from pathlib import Path


def project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return current


def resolve_from_root(path_value: str | Path, root: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return project_root(root) / path

