from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from app.analysis import (build_analysis, build_grid, decision_cutoff_utc, STATUS_MATCHED,
                          STATUS_NO_ACTUAL, STATUS_NO_FORECAST, STATUS_NEITHER)

UTC = timezone.utc
T = pd.Timestamp


def fc(rows):
    df = pd.DataFrame(rows, columns=["start_utc", "publish_utc", "forecast_mw"])
    df["start_raw"] = df["start_utc"]; df["publish_raw"] = df["publish_utc"]
    df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True)
    df["publish_utc"] = pd.to_datetime(df["publish_utc"], utc=True)
    return df


def act(rows):
    df = pd.DataFrame(rows, columns=["start_utc", "actual_mw"])
    df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True)
    return df


def run(forecasts, actuals, day=date(2026, 1, 15), cutoff=time(9, 0)):
    return build_analysis(actuals, forecasts, day, day, cutoff, "Europe/London")


START = "2026-01-15T12:00:00Z"
CUT = "2026-01-14T09:00:00Z"   # 09:00 London on Jan 14 == 09:00 UTC (GMT)


def row(df):
    return df[df["start_utc"] == T(START)].iloc[0]


def test_selects_latest_forecast_published_at_or_before_cutoff():
    f = fc([(START, "2026-01-13T12:00:00Z", 100), (START, "2026-01-14T08:30:00Z", 200)])
    r = row(run(f, act([(START, 150)])))
    assert r["forecast_mw"] == 200 and r["status"] == STATUS_MATCHED
    assert r["publish_utc"] == T("2026-01-14T08:30:00Z")           # audit timestamp preserved


def test_rejects_forecast_published_after_cutoff():
    f = fc([(START, "2026-01-13T12:00:00Z", 100), (START, "2026-01-14T09:00:01Z", 999)])
    r = row(run(f, act([(START, 150)])))
    assert r["forecast_mw"] == 100                                   # 999 would be look-ahead bias
    assert r["latest_forecast_mw"] == 999                            # exposed only as hindsight view


def test_forecast_published_exactly_at_cutoff_is_eligible():
    r = row(run(fc([(START, CUT, 321)]), act([(START, 300)])))
    assert r["forecast_mw"] == 321


def test_only_late_forecast_gives_no_eligible_forecast_and_flag():
    r = row(run(fc([(START, "2026-01-14T10:00:00Z", 5)]), act([(START, 300)])))
    assert r["status"] == STATUS_NO_FORECAST and pd.isna(r["forecast_mw"]) and r["only_after_cutoff"]


def test_missing_actual_and_missing_both():
    r = row(run(fc([(START, "2026-01-14T08:00:00Z", 5)]), act([])))
    assert r["status"] == STATUS_NO_ACTUAL and pd.isna(r["error_mw"])
    r2 = row(run(fc([]), act([])))
    assert r2["status"] == STATUS_NEITHER


def test_forecast_for_other_delivery_time_is_not_used():
    f = fc([("2026-01-15T12:30:00Z", "2026-01-14T08:00:00Z", 777)])
    assert row(run(f, act([(START, 1)])))["status"] == STATUS_NO_FORECAST


def test_duplicate_forecast_rows_do_not_multiply_periods():
    f = fc([(START, "2026-01-14T08:00:00Z", 1), (START, "2026-01-14T08:00:00Z", 2)])
    out = run(f, act([(START, 1), (START, 1)]))
    assert len(out) == 48 and out["start_utc"].is_unique


def test_error_sign_forecast_minus_actual():
    r = row(run(fc([(START, "2026-01-14T08:00:00Z", 250)]), act([(START, 200)])))
    assert r["error_mw"] == 50 and r["abs_error_mw"] == 50


def test_cutoff_is_configurable():
    f = fc([(START, "2026-01-14T10:00:00Z", 5), (START, "2026-01-14T06:00:00Z", 1)])
    assert row(run(f, act([(START, 1)]), cutoff=time(11, 0)))["forecast_mw"] == 5
    assert row(run(f, act([(START, 1)]), cutoff=time(9, 0)))["forecast_mw"] == 1


# ---- timezone / boundaries
def test_cutoff_converts_london_local_to_utc_in_gmt_and_bst():
    assert decision_cutoff_utc(date(2026, 1, 15), time(9, 0), "Europe/London") == datetime(2026, 1, 14, 9, 0, tzinfo=UTC)
    assert decision_cutoff_utc(date(2026, 7, 15), time(9, 0), "Europe/London") == datetime(2026, 7, 14, 8, 0, tzinfo=UTC)


def test_january_delivery_window_boundaries():
    g = build_grid(date(2026, 1, 2), date(2026, 2, 1), time(9), "Europe/London")
    assert len(g) == 31 * 48
    assert g["start_utc"].min() == T("2026-01-02T00:00:00Z") and g["start_utc"].max() == T("2026-02-01T23:30:00Z")


def test_dst_days_have_46_and_50_periods():
    assert len(build_grid(date(2026, 3, 29), date(2026, 3, 29), time(9), "Europe/London")) == 46
    assert len(build_grid(date(2026, 10, 25), date(2026, 10, 25), time(9), "Europe/London")) == 50
