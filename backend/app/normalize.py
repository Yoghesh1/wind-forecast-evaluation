"""Row validation, timestamp normalisation (to tz-aware UTC) and de-duplication.

Elexon timestamps carry a 'Z' suffix (UTC). The original string is kept in
`*_raw` columns for audit. Strings without an offset are assumed UTC and counted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def parse_utc(value: Any) -> tuple[datetime | None, bool]:
    """Return (utc datetime | None, was_naive)."""
    if not isinstance(value, str) or not value:
        return None, False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, False
    naive = dt.tzinfo is None
    if naive:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc), naive


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def normalize_actuals(rows: list[dict]) -> tuple[pd.DataFrame, dict]:
    stats = dict(raw_rows=len(rows), not_wind=0, invalid_rows=0, duplicates_removed=0,
                 conflicting_duplicates=0, naive_timestamps_assumed_utc=0)
    out = []
    for r in rows:
        if r.get("fuelType") not in (None, "WIND"):
            stats["not_wind"] += 1
            continue
        start, naive = parse_utc(r.get("startTime"))
        gen = _num(r.get("generation"))
        if start is None or gen is None:
            stats["invalid_rows"] += 1
            continue
        stats["naive_timestamps_assumed_utc"] += int(naive)
        out.append({"start_utc": start, "start_raw": r["startTime"], "actual_mw": gen})
    df = pd.DataFrame(out, columns=["start_utc", "start_raw", "actual_mw"])
    if df.empty:
        return df, stats
    df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True)
    stats["conflicting_duplicates"] = int((df.groupby("start_utc")["actual_mw"].nunique() > 1).sum())
    before = len(df)
    # Deterministic rule: keep the last row in upstream order for a repeated start time.
    df = df.drop_duplicates("start_utc", keep="last").sort_values("start_utc").reset_index(drop=True)
    stats["duplicates_removed"] = before - len(df)
    return df, stats


def normalize_forecasts(rows: list[dict]) -> tuple[pd.DataFrame, dict]:
    stats = dict(raw_rows=len(rows), invalid_rows=0, duplicates_removed=0,
                 conflicting_duplicates=0, naive_timestamps_assumed_utc=0)
    out = []
    for r in rows:
        start, n1 = parse_utc(r.get("startTime"))
        pub, n2 = parse_utc(r.get("publishTime"))
        gen = _num(r.get("generation"))
        if start is None or pub is None or gen is None:
            stats["invalid_rows"] += 1
            continue
        stats["naive_timestamps_assumed_utc"] += int(n1) + int(n2)
        out.append({"start_utc": start, "publish_utc": pub, "start_raw": r["startTime"],
                    "publish_raw": r["publishTime"], "forecast_mw": gen})
    cols = ["start_utc", "publish_utc", "start_raw", "publish_raw", "forecast_mw"]
    df = pd.DataFrame(out, columns=cols)
    if df.empty:
        return df, stats
    df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True)
    df["publish_utc"] = pd.to_datetime(df["publish_utc"], utc=True)
    key = ["start_utc", "publish_utc"]
    stats["conflicting_duplicates"] = int((df.groupby(key)["forecast_mw"].nunique() > 1).sum())
    before = len(df)
    df = df.drop_duplicates(key, keep="last").sort_values(key).reset_index(drop=True)
    stats["duplicates_removed"] = before - len(df)
    return df, stats
