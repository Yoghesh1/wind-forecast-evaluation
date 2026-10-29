from fastapi.testclient import TestClient

from app.elexon_client import ElexonClient
from app.main import create_app
from app.store import DataStore
import httpx


def test_health_and_metadata(api):
    assert api.get("/api/v1/health").json() == {"status": "ok", "data_state": "ready"}
    md = api.get("/api/v1/metadata").json()
    assert md["unit"] == "MW" and "ASSUMPTION" in md["cutoff_rule"]["status"]
    assert md["decision_window"]["delivery_from"] == "2026-01-02" and md["decision_window"]["delivery_to"] == "2026-02-01"
    assert md["data"]["last_refresh_utc"]


def test_metrics_known_fixture_values(api):
    r = api.get("/api/v1/metrics").json()
    m = r["metrics"]
    assert m["eligible_periods"] == 31 * 48 and m["matched_observations"] == 31 * 48
    assert m["coverage_pct"] == 100.0
    assert abs(m["mae_mw"] - 50) < 1e-9 and abs(m["rmse_mw"] - 50) < 1e-9 and abs(m["bias_mw"] - 50) < 1e-9
    assert r["unit"] == "MW" and "forecast - actual" in r["error_convention"]


def test_cutoff_param_changes_selection(api):
    late = api.get("/api/v1/metrics", params={"cutoff": "11:00"}).json()["metrics"]
    assert abs(late["mae_mw"] - 5) < 1e-9     # 10:30 vintage becomes eligible at an 11:00 cutoff


def test_time_series_schema_and_audit_fields(api):
    p = api.get("/api/v1/time-series", params={"date_from": "2026-01-02", "date_to": "2026-01-02"}).json()
    assert p["count"] == 48
    pt = p["points"][0]
    assert set(pt) == {"start_utc", "actual_mw", "forecast_mw", "error_mw", "publish_utc", "status"}
    assert pt["publish_utc"].startswith("2026-01-01T08:30:00")


def test_delivery_periods_paging_sort_search_filter(api):
    r = api.get("/api/v1/delivery-periods", params={"page_size": 10, "sort_by": "abs_error_mw", "sort_dir": "desc"}).json()
    assert r["total"] == 31 * 48 and len(r["items"]) == 10
    assert api.get("/api/v1/delivery-periods", params={"search": "2026-01-05 12:30"}).json()["total"] == 1
    assert api.get("/api/v1/delivery-periods", params={"status": "no_actual"}).json()["total"] == 0


def test_vintages_show_why_selected(api):
    v = api.get("/api/v1/delivery-periods/vintages", params={"start_utc": "2026-01-10T12:00:00Z"}).json()
    sel = [x for x in v["vintages"] if x["selected"]]
    assert len(v["vintages"]) == 3 and len(sel) == 1 and sel[0]["publish_utc"].startswith("2026-01-09T08:30")
    late = [x for x in v["vintages"] if not x["eligible"]]
    assert len(late) == 1 and late[0]["minutes_before_cutoff"] < 0


def test_forecast_analysis_payload(api):
    a = api.get("/api/v1/forecast-analysis").json()
    assert len(a["daily"]) == 31 and len(a["time_of_day"]) == 48 and a["histogram"] and a["insights"]
    assert len(a["largest_errors"]) == 10
    assert a["hindsight_comparison"]["latest_available_mae_mw"] == 5


def test_validation_errors(api):
    assert api.get("/api/v1/metrics", params={"cutoff": "25:00"}).status_code == 422
    assert api.get("/api/v1/metrics", params={"date_from": "2026-01-10", "date_to": "2026-01-05"}).status_code == 422
    assert api.get("/api/v1/metrics", params={"date_from": "2025-12-01"}).status_code == 422
    assert api.get("/api/v1/delivery-periods", params={"sort_by": "nope"}).status_code == 422
    assert api.get("/api/v1/delivery-periods/vintages", params={"start_utc": "2030-01-01T00:00:00Z"}).status_code == 404


def test_503_when_no_data_and_upstream_failure_not_masked(settings):
    def boom(req): return httpx.Response(503)
    client = ElexonClient("http://x", http=httpx.Client(transport=httpx.MockTransport(boom)),
                          max_retries=1, sleep=lambda s: None)
    store = DataStore(settings, client)
    store.refresh()
    app = TestClient(create_app(settings, store))
    assert store.state == "error" and "503" in store.last_error
    r = app.get("/api/v1/metrics")
    assert r.status_code == 503 and r.json()["detail"]["state"] == "error"   # no synthetic fallback


def test_empty_upstream_reports_warnings_and_zero_coverage(settings):
    client = ElexonClient("http://x", http=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=[]))), sleep=lambda s: None)
    store = DataStore(settings, client)
    store.refresh()
    app = TestClient(create_app(settings, store))
    md = app.get("/api/v1/metadata").json()
    assert md["data"]["report"]["warnings"]
    m = app.get("/api/v1/metrics").json()["metrics"]
    assert m["matched_observations"] == 0 and m["mae_mw"] is None and m["coverage_pct"] == 0.0


def test_failed_refresh_keeps_previous_good_data(api, store_with_fixture):
    store = store_with_fixture
    store.client._http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    store.client.max_retries = 0
    store.refresh()
    assert store.state == "ready" and store.last_error
    assert api.get("/api/v1/metrics").json()["metrics"]["matched_observations"] == 31 * 48


def test_refresh_endpoint_and_token(settings, store_with_fixture, monkeypatch):
    from dataclasses import replace
    s = replace(settings, refresh_token="s3cret")
    app = TestClient(create_app(s, store_with_fixture))
    assert app.post("/api/v1/data/refresh").status_code == 401
    assert app.post("/api/v1/data/refresh", headers={"X-Refresh-Token": "s3cret"}).status_code == 202
    assert "s3cret" not in app.get("/api/v1/metadata").text


def test_cache_roundtrip(settings, store_with_fixture):
    fresh = DataStore(settings, store_with_fixture.client)
    assert fresh.load_cache() and len(fresh.dataset.forecasts) == len(store_with_fixture.dataset.forecasts)
