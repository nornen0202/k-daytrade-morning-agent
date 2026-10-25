from __future__ import annotations

from datetime import datetime


def temporal_status(stamp: datetime | None, reference: datetime, hours: float = 48) -> str:
    if stamp is None or stamp.utcoffset() is None or reference.utcoffset() is None:
        return "insufficient"
    age = (reference - stamp).total_seconds()
    if age < 0:
        return "insufficient"
    return "stale" if age > hours * 3600 else "ok"
