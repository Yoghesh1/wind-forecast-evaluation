"""Decision-time forecast selection.

For each 30-minute delivery period (startTime):
  cutoff   = (delivery local date - lead_days) at `cutoff` local market time, converted to UTC
  forecast = the forecast row for the SAME startTime with the greatest publishTime <= cutoff
This uses an as-of (backward) join, so every delivery period gets at most one forecast
and no many-to-many fan-out is possible. Forecasts published after the cutoff are never used.
Nothing is interpolated or zero-filled.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

UTC = timezone.utc
TS = "datetime64[ns, UTC]"

STATUS_MATCHED = "matched"
STATUS_NO_FORECAST = "no_eligible_forecast"
STATUS_NO_ACTUAL = "no_actual"
STATUS_NEITHER = "no_forecast_and_no_actual"


def decision_cutoff_utc(delivery_date: date, cutoff: time, tz: str, lead_days: int = 1) -> datetime:
    """UTC instant of the decision cutoff for a delivery (local) date."""
    decision_day = delivery_date - timedelta(days=lead_days)
    return datetime.combine(decision_day, cutoff, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def build_grid(d_from: date, d_to: date, cutoff: time, tz: str, lead_days: int = 1) -> pd.DataFrame:
    """Every 30-minute delivery period for local days d_from..d_to inclusive (DST-safe)."""
    zone = ZoneInfo(tz)
    frames = []
    d = d_from
    while d <= d_to:
        s = datetime.combine(d, time(0), tzinfo=zone).astimezone(UTC)
        e = datetime.combine(d + timedelta(days=1), time(0), tzinfo=zone).astimezone(UTC)
        starts = pd.date_range(s, e, freq="30min", inclusive="left", tz="UTC")
        frames.append(pd.DataFrame({
            "start_utc": starts,
            "delivery_date": d.isoformat(),
            "cutoff_utc": pd.Timestamp(decision_cutoff_utc(d, cutoff, tz, lead_days)),
        }))
        d += timedelta(days=1)
    grid = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["start_utc", "delivery_date", "cutoff_utc"])
    grid["start_utc"] = grid["start_utc"].astype(TS)
    grid["cutoff_utc"] = grid["cutoff_utc"].astype(TS)
    return grid


def build_analysis(actuals: pd.DataFrame, forecasts: pd.DataFrame, d_from: date, d_to: date,
                   cutoff: time, tz: str, lead_days: int = 1) -> pd.DataFrame:
    grid = build_grid(d_from, d_to, cutoff, tz, lead_days)

    fc = forecasts[["start_utc", "publish_utc", "forecast_mw"]].copy()
    fc["start_utc"] = fc["start_utc"].astype(TS)
    fc["publish_utc"] = fc["publish_utc"].astype(TS)
    fc = fc.drop_duplicates(["start_utc", "publish_utc"], keep="last")

    g = grid.sort_values("cutoff_utc")
    sel = pd.merge_asof(
        g, fc.sort_values("publish_utc"),
        left_on="cutoff_utc", right_on="publish_utc", by="start_utc",
        direction="backward", allow_exact_matches=True,
    )

    # Hindsight view (NOT decision-valid): newest forecast ever published for the period.
    latest = (fc.sort_values("publish_utc").groupby("start_utc", as_index=False).last()
                .rename(columns={"publish_utc": "latest_publish_utc", "forecast_mw": "latest_forecast_mw"}))
    sel = sel.merge(latest, on="start_utc", how="left", validate="many_to_one")

    act = actuals[["start_utc", "actual_mw"]].copy()
    act["start_utc"] = act["start_utc"].astype(TS)
    sel = sel.merge(act.drop_duplicates("start_utc", keep="last"), on="start_utc", how="left",
                    validate="many_to_one")

    sel = sel.sort_values("start_utc").reset_index(drop=True)
    sel["error_mw"] = sel["forecast_mw"] - sel["actual_mw"]          # forecast - actual
    sel["abs_error_mw"] = sel["error_mw"].abs()
    sel["horizon_h"] = (sel["start_utc"] - sel["publish_utc"]).dt.total_seconds() / 3600
    has_f, has_a = sel["forecast_mw"].notna(), sel["actual_mw"].notna()
    sel["status"] = np.select(
        [has_f & has_a, ~has_f & has_a, has_f & ~has_a],
        [STATUS_MATCHED, STATUS_NO_FORECAST, STATUS_NO_ACTUAL],
        default=STATUS_NEITHER,
    )
    # Audit flag: a forecast exists, but only published after the cutoff.
    sel["only_after_cutoff"] = (~has_f) & sel["latest_publish_utc"].notna()
    return sel


# ---------------------------------------------------------------- metrics

def compute_metrics(df: pd.DataFrame, mape_min_actual_mw: float) -> dict:
    eligible = int(len(df))
    m = df[df["status"] == STATUS_MATCHED]
    n = int(len(m))
    out: dict = {
        "eligible_periods": eligible,
        "matched_observations": n,
        "coverage_pct": round(100 * n / eligible, 2) if eligible else None,
        "missing_forecast": int((df["status"].isin([STATUS_NO_FORECAST, STATUS_NEITHER])).sum()),
        "missing_actual": int((df["status"].isin([STATUS_NO_ACTUAL, STATUS_NEITHER])).sum()),
        "mae_mw": None, "rmse_mw": None, "bias_mw": None,
        "mape_pct": None, "mape_observations": 0, "mape_excluded": n,
        "mape_min_actual_mw": mape_min_actual_mw,
    }
    if n == 0:
        return out
    e = m["error_mw"].to_numpy(dtype=float)
    out["mae_mw"] = float(np.mean(np.abs(e)))
    out["rmse_mw"] = float(np.sqrt(np.mean(e**2)))
    out["bias_mw"] = float(np.mean(e))
    ok = m["actual_mw"].to_numpy(dtype=float) >= mape_min_actual_mw
    if ok.any():
        out["mape_pct"] = float(np.mean(np.abs(e[ok]) / m["actual_mw"].to_numpy(dtype=float)[ok]) * 100)
    out["mape_observations"] = int(ok.sum())
    out["mape_excluded"] = int(n - ok.sum())
    return out


def daily_metrics(df: pd.DataFrame) -> list[dict]:
    rows = []
    for day, g in df.groupby("delivery_date", sort=True):
        m = g[g["status"] == STATUS_MATCHED]
        n = len(m)
        e = m["error_mw"].to_numpy(dtype=float)
        rows.append({
            "date": day, "eligible_periods": int(len(g)), "matched_observations": int(n),
            "coverage_pct": round(100 * n / len(g), 2),
            "mae_mw": float(np.mean(np.abs(e))) if n else None,
            "rmse_mw": float(np.sqrt(np.mean(e**2))) if n else None,
            "bias_mw": float(np.mean(e)) if n else None,
        })
    return rows


def time_of_day_metrics(df: pd.DataFrame, tz: str) -> list[dict]:
    m = df[df["status"] == STATUS_MATCHED].copy()
    if m.empty:
        return []
    local = m["start_utc"].dt.tz_convert(tz)
    m["slot"] = local.dt.strftime("%H:%M")
    return [{"slot": s, "matched_observations": int(len(g)),
             "mae_mw": float(g["abs_error_mw"].mean()), "bias_mw": float(g["error_mw"].mean())}
            for s, g in m.groupby("slot", sort=True)]


def error_histogram(df: pd.DataFrame, bin_width_mw: float = 250.0) -> list[dict]:
    e = df.loc[df["status"] == STATUS_MATCHED, "error_mw"].to_numpy(dtype=float)
    if e.size == 0:
        return []
    lo = np.floor(e.min() / bin_width_mw) * bin_width_mw
    hi = np.ceil((e.max() + 1e-9) / bin_width_mw) * bin_width_mw
    edges = np.arange(lo, hi + bin_width_mw, bin_width_mw)
    counts, edges = np.histogram(e, bins=edges)
    return [{"from_mw": float(edges[i]), "to_mw": float(edges[i + 1]), "count": int(c)}
            for i, c in enumerate(counts)]


def hindsight_comparison(df: pd.DataFrame) -> dict:
    """MAE of newest-ever forecast vs decision-time forecast on the SAME matched periods.
    The first is look-ahead biased and shown only to size that bias."""
    m = df[(df["status"] == STATUS_MATCHED) & df["latest_forecast_mw"].notna()]
    if m.empty:
        return {"observations": 0, "decision_time_mae_mw": None, "latest_available_mae_mw": None}
    return {
        "observations": int(len(m)),
        "decision_time_mae_mw": float((m["forecast_mw"] - m["actual_mw"]).abs().mean()),
        "latest_available_mae_mw": float((m["latest_forecast_mw"] - m["actual_mw"]).abs().mean()),
    }
