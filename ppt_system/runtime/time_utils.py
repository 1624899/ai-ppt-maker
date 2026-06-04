from __future__ import annotations

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_timestamp_millis() -> str:
    return utc_now_naive().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def utc_iso_timestamp(timespec: str = "seconds") -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec=timespec) + "Z"
