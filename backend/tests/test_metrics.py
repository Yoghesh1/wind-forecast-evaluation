import math

import pandas as pd
import pytest

from app.analysis import compute_metrics, error_histogram, daily_metrics


def frame(pairs, statuses=None):
    """pairs: (forecast, actual) tuples; None values = missing."""
    rows = []
    for i, (f, a) in enumerate(pairs):
        st = "matched" if f is not None and a is not None else (
            "no_actual" if a is None and f is not None else "no_eligible_forecast" if f is None and a is not None
            else "no_forecast_and_no_actual")
        rows.append(dict(delivery_date="2026-01-02", forecast_mw=f, actual_mw=a, status=st,
                         error_mw=(f - a) if st == "matched" else math.nan,
                         abs_error_mw=abs(f - a) if st == "matched" else math.nan))
    return pd.DataFrame(rows)


def test_mae_rmse_bias_known_values():
    # errors (forecast - actual): +10, -20, +30  -> MAE 20, RMSE sqrt(1400/3), bias 20/3
    m = compute_metrics(frame([(110, 100), (180, 200), (330, 300)]), 100)
    assert m["mae_mw"] == pytest.approx(20.0)
    assert m["rmse_mw"] == pytest.approx(math.sqrt(1400 / 3))
    assert m["bias_mw"] == pytest.approx(20 / 3)
    assert m["matched_observations"] == 3 and m["coverage_pct"] == 100.0


def test_bias_sign_over_and_under_forecast():
    assert compute_metrics(frame([(150, 100)]), 1)["bias_mw"] == 50      # over-forecast positive
    assert compute_metrics(frame([(50, 100)]), 1)["bias_mw"] == -50      # under-forecast negative


def test_mape_excludes_zero_and_near_zero_actuals():
    # actuals 0 and 50 are below the 100 MW threshold -> excluded; only (120,100) counts: 20%
    m = compute_metrics(frame([(10, 0), (60, 50), (120, 100)]), 100)
    assert m["mape_pct"] == pytest.approx(20.0)
    assert m["mape_observations"] == 1 and m["mape_excluded"] == 2


def test_mape_none_when_all_actuals_near_zero():
    m = compute_metrics(frame([(5, 0), (5, 1)]), 100)
    assert m["mape_pct"] is None and m["mape_observations"] == 0


def test_coverage_and_exclusions_are_transparent():
    m = compute_metrics(frame([(110, 100), (None, 100), (100, None), (None, None)]), 100)
    assert m["eligible_periods"] == 4 and m["matched_observations"] == 1
    assert m["coverage_pct"] == 25.0
    assert m["missing_forecast"] == 2 and m["missing_actual"] == 2
    assert m["mae_mw"] == 10   # unmatched rows are never zero-filled into the average


def test_no_matches_yields_none_not_zero():
    m = compute_metrics(frame([(None, 100)]), 100)
    assert m["mae_mw"] is None and m["rmse_mw"] is None and m["bias_mw"] is None


def test_daily_and_histogram():
    df = frame([(110, 100), (90, 100)])
    d = daily_metrics(df)[0]
    assert d["mae_mw"] == 10 and d["bias_mw"] == 0
    assert sum(b["count"] for b in error_histogram(df, 10)) == 2
