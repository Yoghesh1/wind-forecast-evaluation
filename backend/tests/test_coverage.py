"""Regression tests for the coverage warning "744 distinct delivery periods; 1488 expected".

Root cause: the expected count was hard-coded to 30-minute resolution for BOTH datasets, but WINDFOR
supplies one forecast per hour. 31 days x 24 = 744 is a correct count of distinct hourly start times,
so the warning was a wrong expectation, not a counting bug. All data here is synthetic TEST FIXTURE data.
"""
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from app.analysis import (STATUS_MATCHED, STATUS_NO_FORECAST, build_analysis, compute_metrics)
from app.normalize import normalize_actuals, normalize_forecasts
from app.store import coverage_report
from tests.fixtures import make_rows, z

TZ = "Europe/London"
UTC = timezone.utc
JAN = (date(2026, 1, 2), date(2026, 2, 1))


def raw(first=JAN[0], last=JAN[1]):
    return make_rows(first, last)


def hourly(rows):
    return [r for r in rows if r["startTime"][14:16] == "00"]


def report(a, f, window=JAN):
    act, _ = normalize_actuals(a)
    fc, _ = normalize_forecasts(f)
    return coverage_report(act, fc, window[0], window[1], TZ), act, fc


# ---- the discovered root cause
def test_hourly_forecasts_reproduce_744_and_are_explained_not_called_a_gap():
    a, f = raw()
    rep, _, _ = report(a, hourly(f))
    c = rep["coverage"]
    assert c["forecasts_distinct_periods_in_window"] == 744 and c["window_half_hour_periods"] == 1488
    assert c["forecasts_resolution_minutes"] == 60 and c["actuals_resolution_minutes"] == 30
    assert c["forecasts_start_minute_of_hour_counts"] == {0: 744}        # lets a reviewer verify cadence
    assert len(rep["warnings"]) == 1                                      # warning is NOT hidden...
    w = rep["warnings"][0]
    assert "744" in w and "1488" in w and "not interpolated" in w          # ...it states the real situation
    assert "expected at the observed" not in w                             # and is not reported as a data gap


def test_half_hourly_forecasts_produce_no_warning():
    a, f = raw()
    assert report(a, f)[0]["warnings"] == []


def test_hourly_forecast_halves_coverage_and_never_fills_the_half_hours():
    a, f = raw()
    _, act, fc = report(a, hourly(f))
    df = build_analysis(act, fc, *JAN, time(9), TZ)
    on_hour = df["start_utc"].dt.minute == 0
    assert (df.loc[on_hour, "status"] == STATUS_MATCHED).all()
    off = df[~on_hour]
    assert (off["status"] == STATUS_NO_FORECAST).all() and off["forecast_mw"].isna().all()   # no interpolation
    assert not off["only_after_cutoff"].any()                    # structural: no row ever exists for :30
    m = compute_metrics(df, 100)
    assert m["eligible_periods"] == 1488 and m["matched_observations"] == 744 and m["coverage_pct"] == 50.0
    assert abs(m["mae_mw"] - 50) < 1e-9                          # metrics use matched periods only


# ---- missing / duplicate intervals
def test_genuine_forecast_gap_is_reported_as_gap():
    a, f = raw()
    drop = {z(datetime(2026, 1, 10, 12, 0, tzinfo=UTC)), z(datetime(2026, 1, 10, 12, 30, tzinfo=UTC))}
    rep, _, _ = report(a, [r for r in f if r["startTime"] not in drop])
    assert any("gap of 2" in w and "forecasts" in w for w in rep["warnings"])


def test_genuine_gap_in_hourly_forecasts_is_measured_against_hourly_cadence():
    a, f = raw()
    h = [r for r in hourly(f) if r["startTime"] != z(datetime(2026, 1, 10, 12, 0, tzinfo=UTC))]
    ws = report(a, h)[0]["warnings"]
    assert any("743 distinct" in w and "744 expected at the observed 60-minute" in w and "gap of 1" in w for w in ws)


def test_missing_actual_intervals_reported():
    a, f = raw()
    a = [r for r in a if r["startTime"] != z(datetime(2026, 1, 5, 3, 30, tzinfo=UTC))]
    ws = report(a, f)[0]["warnings"]
    assert any(w.startswith("actuals: 1487 distinct") and "gap of 1" in w for w in ws)


def test_duplicate_intervals_do_not_inflate_counts():
    a, f = raw()
    rep, act, fc = report(a + a[:50], f + f[:50])
    assert rep["coverage"]["actuals_distinct_periods_in_window"] == 1488
    assert rep["coverage"]["forecasts_distinct_periods_in_window"] == 1488
    assert len(act) == 1488 and rep["warnings"] == []


def test_rows_outside_delivery_window_are_not_counted():
    # actuals for 1 Jan and 2 Feb are fetched (window padding) but must not count as in-window
    a, f = make_rows(date(2026, 1, 1), date(2026, 2, 2))
    rep, act, _ = report(a, f)
    assert len(act) == 33 * 48 and rep["coverage"]["actuals_distinct_periods_in_window"] == 1488


def test_empty_responses_fail_visibly():
    rep, _, _ = report([], [])
    assert len(rep["warnings"]) == 2 and all("no" in w.lower() for w in rep["warnings"])


# ---- identification consistency across datasets
def test_equivalent_timestamp_spellings_match_one_interval():
    a = [{"fuelType": "WIND", "startTime": "2026-01-15T12:00:00Z", "generation": 100}]
    f = [{"startTime": "2026-01-15T12:00:00+00:00", "publishTime": "2026-01-14T08:00:00", "generation": 130}]
    act, _ = normalize_actuals(a); fc, fst = normalize_forecasts(f)
    assert fst["naive_timestamps_assumed_utc"] == 1                       # naive publishTime is counted, assumed UTC
    df = build_analysis(act, fc, date(2026, 1, 15), date(2026, 1, 15), time(9), TZ)
    r = df[df["start_utc"] == pd.Timestamp("2026-01-15T12:00:00Z")].iloc[0]
    assert r["status"] == STATUS_MATCHED and r["error_mw"] == 30


# ---- cutoff boundaries (GMT and BST) with hourly forecasts
def _one(delivery, pub, cutoff=time(9)):
    start = f"{delivery}T12:00:00Z"
    f = [{"startTime": start, "publishTime": pub, "generation": 1}]
    a = [{"fuelType": "WIND", "startTime": start, "generation": 1}]
    act, _ = normalize_actuals(a); fc, _ = normalize_forecasts(f)
    d = date.fromisoformat(delivery)
    df = build_analysis(act, fc, d, d, cutoff, TZ)
    return df[df["start_utc"] == pd.Timestamp(start)].iloc[0]["status"]


def test_cutoff_boundary_gmt_winter():          # 09:00 London == 09:00 UTC
    assert _one("2026-01-15", "2026-01-14T08:59:59Z") == STATUS_MATCHED
    assert _one("2026-01-15", "2026-01-14T09:00:00Z") == STATUS_MATCHED
    assert _one("2026-01-15", "2026-01-14T09:00:01Z") == STATUS_NO_FORECAST


def test_cutoff_boundary_bst_summer():          # 09:00 London == 08:00 UTC
    assert _one("2026-07-15", "2026-07-14T08:00:00Z") == STATUS_MATCHED
    assert _one("2026-07-15", "2026-07-14T08:00:01Z") == STATUS_NO_FORECAST


def test_cutoff_uses_decision_date_local_time_across_spring_forward():
    # decision 28 Mar (GMT) -> delivery 29 Mar (clocks go forward): cutoff is the 28th at 09:00 GMT
    assert _one("2026-03-29", "2026-03-28T09:00:00Z") == STATUS_MATCHED
    assert _one("2026-03-29", "2026-03-28T09:00:01Z") == STATUS_NO_FORECAST
    # decision 29 Mar (BST, 08:00Z) -> delivery 30 Mar
    assert _one("2026-03-30", "2026-03-29T08:00:00Z") == STATUS_MATCHED
    assert _one("2026-03-30", "2026-03-29T08:00:01Z") == STATUS_NO_FORECAST


def test_cutoff_across_autumn_fall_back():
    # decision 24 Oct (BST, 08:00Z) -> delivery 25 Oct; decision 25 Oct (GMT, 09:00Z) -> delivery 26 Oct
    assert _one("2026-10-25", "2026-10-24T08:00:00Z") == STATUS_MATCHED
    assert _one("2026-10-25", "2026-10-24T08:00:01Z") == STATUS_NO_FORECAST
    assert _one("2026-10-26", "2026-10-25T09:00:00Z") == STATUS_MATCHED
    assert _one("2026-10-26", "2026-10-25T09:00:01Z") == STATUS_NO_FORECAST


# ---- DST days: expected counts follow the real UTC span
def _day(d):
    start = datetime.combine(d, time(0), tzinfo=__import__("zoneinfo").ZoneInfo(TZ)).astimezone(UTC)
    end = datetime.combine(d + timedelta(days=1), time(0), tzinfo=__import__("zoneinfo").ZoneInfo(TZ)).astimezone(UTC)
    rows, t = [], start
    while t < end:
        rows.append(t); t += timedelta(minutes=30)
    return rows


def test_dst_days_expect_46_and_50_periods_and_no_false_gap():
    for d, n in ((date(2026, 3, 29), 46), (date(2026, 10, 25), 50), (date(2026, 1, 15), 48)):
        ts = _day(d)
        a = [{"fuelType": "WIND", "startTime": z(t), "generation": 1} for t in ts]
        f = [{"startTime": z(t), "publishTime": z(ts[0] - timedelta(days=1)), "generation": 1} for t in ts]
        rep, _, _ = report(a, f, (d, d))
        assert rep["coverage"]["window_half_hour_periods"] == n == len(ts)
        assert rep["coverage"]["actuals_distinct_periods_in_window"] == n and rep["warnings"] == []


def test_dst_day_missing_interval_is_a_gap_of_one():
    ts = _day(date(2026, 3, 29))
    a = [{"fuelType": "WIND", "startTime": z(t), "generation": 1} for t in ts[:-1]]
    rep, _, _ = report(a, [], (date(2026, 3, 29), date(2026, 3, 29)))
    assert any("actuals: 45 distinct" in w and "46 expected" in w for w in rep["warnings"])


def test_stale_cache_warning_is_recomputed_on_load(store_with_fixture):
    import json
    from app.store import DataStore
    s = store_with_fixture
    p = json.loads(s.settings.cache_path.read_text())
    p["report"]["warnings"] = ["forecasts: 744 distinct delivery periods in 2026-01-02..2026-02-01; 1488 expected at 30-minute resolution."]
    s.settings.cache_path.write_text(json.dumps(p))
    fresh = DataStore(s.settings, s.client)
    assert fresh.load_cache()
    assert fresh.dataset.report["warnings"] == []          # fixture is half-hourly, so the old text must not survive
    assert fresh.dataset.report["coverage"]["forecasts_resolution_minutes"] == 30
