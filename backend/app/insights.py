"""Deterministic insights. Every sentence is computed from the supplied data; none is hardcoded."""
from __future__ import annotations

import pandas as pd

from .analysis import STATUS_MATCHED


def build_insights(metrics: dict, daily: list[dict], df: pd.DataFrame, hours: list[dict], hind: dict) -> list[dict]:
    out: list[dict] = []
    n = metrics["matched_observations"]
    if n == 0:
        return [{"id": "no-data", "text": "No matched forecast/actual periods in the selected range.", "sample_size": 0}]

    bias = metrics["bias_mw"]
    m = df[df["status"] == STATUS_MATCHED]
    over = int((m["error_mw"] > 0).sum())
    direction = "over-forecast" if bias > 0 else "under-forecast" if bias < 0 else "neither over- nor under-forecast"
    out.append({"id": "bias",
                "text": (f"On average the decision-time forecast {direction} wind by {abs(bias):,.0f} MW "
                         f"(forecast − actual); {100*over/n:.0f}% of periods were over-forecast."),
                "sample_size": n})

    days = [d for d in daily if d["mae_mw"] is not None]
    if days:
        worst = max(days, key=lambda d: d["mae_mw"])
        best = min(days, key=lambda d: d["mae_mw"])
        out.append({"id": "worst-day",
                    "text": f"Highest daily MAE: {worst['date']} at {worst['mae_mw']:,.0f} MW "
                            f"(bias {worst['bias_mw']:+,.0f} MW).",
                    "sample_size": worst["matched_observations"]})
        out.append({"id": "best-day",
                    "text": f"Lowest daily MAE: {best['date']} at {best['mae_mw']:,.0f} MW.",
                    "sample_size": best["matched_observations"]})

    top = m.loc[m["abs_error_mw"].idxmax()]
    out.append({"id": "largest-error",
                "text": (f"Largest single deviation: {top['error_mw']:+,.0f} MW at "
                         f"{top['start_utc'].strftime('%Y-%m-%d %H:%M')} UTC "
                         f"(forecast {top['forecast_mw']:,.0f} MW vs actual {top['actual_mw']:,.0f} MW)."),
                "sample_size": n})

    if hours:
        wh = max(hours, key=lambda h: h["mae_mw"])
        out.append({"id": "worst-slot",
                    "text": f"Largest MAE by local time of day: {wh['slot']} at {wh['mae_mw']:,.0f} MW "
                            f"(across {wh['matched_observations']} days).",
                    "sample_size": wh["matched_observations"]})

    missing_f, missing_a = metrics["missing_forecast"], metrics["missing_actual"]
    if missing_f or missing_a:
        lowcov = sorted([d for d in daily if d["coverage_pct"] < 100], key=lambda d: d["coverage_pct"])[:3]
        days_txt = ", ".join(f"{d['date']} ({d['coverage_pct']:.0f}%)" for d in lowcov)
        late = int(df["only_after_cutoff"].sum())
        out.append({"id": "coverage",
                    "text": (f"{missing_f} periods have no eligible forecast ({late} had forecasts only "
                             f"after the cutoff) and {missing_a} have no actual. Lowest coverage: {days_txt}."),
                    "sample_size": metrics["eligible_periods"]})
    else:
        out.append({"id": "coverage", "text": "Every eligible period has both a forecast and an actual.",
                    "sample_size": metrics["eligible_periods"]})

    if hind.get("observations"):
        d, l = hind["decision_time_mae_mw"], hind["latest_available_mae_mw"]
        out.append({"id": "lookahead",
                    "text": (f"For reference, using the newest forecast published after the decision would give "
                             f"MAE {l:,.0f} MW vs {d:,.0f} MW at decision time. That figure is look-ahead biased and "
                             f"must not be used for procurement evaluation."),
                    "sample_size": hind["observations"]})
    return out
