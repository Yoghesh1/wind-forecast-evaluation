import httpx
import pytest

from app.elexon_client import ElexonClient, ElexonError
from app.normalize import normalize_actuals, normalize_forecasts, parse_utc


def test_parse_utc_variants():
    d, naive = parse_utc("2026-01-15T12:00:00Z");           assert d.isoformat() == "2026-01-15T12:00:00+00:00" and not naive
    d, _ = parse_utc("2026-01-15T12:00:00+01:00");          assert d.isoformat() == "2026-01-15T11:00:00+00:00"
    d, naive = parse_utc("2026-01-15T12:00:00");            assert d.tzinfo is not None and naive
    assert parse_utc("garbage")[0] is None and parse_utc(None)[0] is None


def test_actuals_filter_validate_dedupe():
    rows = [
        {"fuelType": "WIND", "startTime": "2026-01-15T12:00:00Z", "generation": 100},
        {"fuelType": "WIND", "startTime": "2026-01-15T12:00:00Z", "generation": 120},   # conflicting dup
        {"fuelType": "CCGT", "startTime": "2026-01-15T12:00:00Z", "generation": 9},
        {"fuelType": "WIND", "startTime": "2026-01-15T12:30:00Z"},                      # missing generation
        {"fuelType": "WIND", "generation": 5},                                          # missing time
        {"fuelType": "WIND", "startTime": "2026-01-15T13:00:00Z", "generation": 0},     # zero is a real value
    ]
    df, s = normalize_actuals(rows)
    assert len(df) == 2 and df.loc[0, "actual_mw"] == 120                              # keep-last rule
    assert s["not_wind"] == 1 and s["invalid_rows"] == 2
    assert s["duplicates_removed"] == 1 and s["conflicting_duplicates"] == 1
    assert df["start_utc"].dt.tz is not None and (df["actual_mw"] == 0).any()


def test_forecasts_dedupe_and_invalid():
    rows = [{"startTime": "2026-01-15T12:00:00Z", "publishTime": "2026-01-14T08:00:00Z", "generation": 1},
            {"startTime": "2026-01-15T12:00:00Z", "publishTime": "2026-01-14T08:00:00Z", "generation": 1},
            {"startTime": "2026-01-15T12:00:00Z", "generation": 1}]
    df, s = normalize_forecasts(rows)
    assert len(df) == 1 and s["duplicates_removed"] == 1 and s["invalid_rows"] == 1


def test_empty_inputs():
    assert normalize_actuals([])[0].empty and normalize_forecasts([])[0].empty


def mk(handler, **kw):
    return ElexonClient("http://x", http=httpx.Client(transport=httpx.MockTransport(handler)),
                        sleep=lambda s: None, **kw)


def test_retries_transient_then_succeeds():
    calls = []
    def h(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json=[{"a": 1}])
    assert mk(h)._get_rows("/p", {}) == [{"a": 1}] and len(calls) == 3


def test_gives_up_after_max_retries():
    calls = []
    def h(req): calls.append(1); return httpx.Response(500)
    with pytest.raises(ElexonError):
        mk(h, max_retries=2)._get_rows("/p", {})
    assert len(calls) == 3


def test_timeout_is_retried_then_raised():
    def h(req): raise httpx.ReadTimeout("slow")
    with pytest.raises(ElexonError):
        mk(h, max_retries=1)._get_rows("/p", {})


def test_client_error_not_retried():
    calls = []
    def h(req): calls.append(1); return httpx.Response(400, text="bad")
    with pytest.raises(ElexonError):
        mk(h)._get_rows("/p", {})
    assert len(calls) == 1


def test_accepts_envelope_array_and_empty_and_rejects_bad_shape():
    assert mk(lambda r: httpx.Response(200, json={"data": [{"a": 1}]}))._get_rows("/p", {}) == [{"a": 1}]
    assert mk(lambda r: httpx.Response(200, json=[]))._get_rows("/p", {}) == []
    with pytest.raises(ElexonError):
        mk(lambda r: httpx.Response(200, json={"oops": 1}))._get_rows("/p", {})
    with pytest.raises(ElexonError):
        mk(lambda r: httpx.Response(200, text="<html>"))._get_rows("/p", {})


def test_windows_are_bounded_and_cover_range():
    from datetime import date, datetime, timezone
    seen = []
    def h(req):
        seen.append(dict(req.url.params)); return httpx.Response(200, json=[])
    c = mk(h)
    c.fetch_actual_wind(date(2026, 1, 2), date(2026, 2, 1))
    assert len(seen) == 5 and seen[0]["settlementDateFrom"] == "2026-01-02" and seen[-1]["settlementDateTo"] == "2026-02-01"
    assert all(p["fuelType"] == "WIND" for p in seen)
    seen.clear()
    c.fetch_wind_forecasts(datetime(2025, 12, 30, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert len(seen) == 17 and seen[0]["publishDateTimeFrom"] == "2025-12-30T00:00:00Z"
    assert seen[-1]["publishDateTimeTo"] == "2026-02-01T00:00:00Z"
