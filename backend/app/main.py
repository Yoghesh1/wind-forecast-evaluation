"""FastAPI routes. Thin: validation + serialisation only; logic lives in analysis/store modules."""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from typing import Literal

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import analysis as A
from .config import Settings, get_settings
from .elexon_client import ElexonClient
from .insights import build_insights
from .schemas import (DeliveryPeriodsResponse, ForecastAnalysis, Health, MetricsResponse, RefreshAck,
                      TimeSeriesResponse, VintageResponse)
from .store import DataStore

log = logging.getLogger("wind")
UNIT = "MW"
ERR = "error = forecast - actual (positive = over-forecast)"
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def create_app(settings: Settings | None = None, store: DataStore | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = store or DataStore(settings, ElexonClient(settings.elexon_base_url, settings.request_timeout_s,
                                                      settings.max_retries, settings.backoff_base_s))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loaded = store.load_cache()
        if not loaded and settings.auto_refresh_on_start:
            import threading
            threading.Thread(target=store.refresh, daemon=True).start()
        yield

    app = FastAPI(title="Wind Forecast Decision-Time Evaluation API", version="1.0.0", lifespan=lifespan,
                  description="National GB wind actuals (Elexon FUELHH) vs forecasts (Elexon WINDFOR) "
                              "selected by publication time relative to a configurable decision cutoff.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["*"])

    # ---------------------------------------------------------- helpers
    def parse_cutoff(cutoff: str | None) -> time:
        if cutoff is None:
            return settings.default_cutoff
        if not HHMM.match(cutoff):
            raise HTTPException(422, "cutoff must be HH:MM (24h, local market time)")
        return time(int(cutoff[:2]), int(cutoff[3:]))

    def get_df(cutoff: str | None, date_from: date | None, date_to: date | None) -> tuple[pd.DataFrame, time]:
        if store.dataset is None:
            code = 503
            raise HTTPException(code, {"state": store.state, "error": store.last_error,
                                       "message": "Data not loaded yet" if store.state != "error"
                                       else "Initial Elexon download failed"})
        c = parse_cutoff(cutoff)
        lo, hi = date_from or settings.delivery_start, date_to or settings.delivery_end
        if lo > hi:
            raise HTTPException(422, "date_from must be <= date_to")
        if lo < settings.delivery_start or hi > settings.delivery_end:
            raise HTTPException(422, f"dates must be within {settings.delivery_start}..{settings.delivery_end} "
                                     "(delivery dates for the configured decision window)")
        df = store.analysis(c)
        return df[(df["delivery_date"] >= lo.isoformat()) & (df["delivery_date"] <= hi.isoformat())], c

    def iso(v) -> str | None:
        return None if v is None or pd.isna(v) else pd.Timestamp(v).isoformat()

    def num(v) -> float | None:
        return None if v is None or pd.isna(v) else float(v)

    def refresh_guard(x_refresh_token: str | None = Header(default=None)) -> None:
        if settings.refresh_token and x_refresh_token != settings.refresh_token:
            raise HTTPException(401, "Invalid or missing X-Refresh-Token")

    # ---------------------------------------------------------- routes
    @app.get("/api/v1/health", response_model=Health, tags=["system"])
    def health():
        return Health(status="ok", data_state=store.state)

    @app.get("/api/v1/metadata", tags=["system"])
    def metadata():
        d = store.dataset
        return {
            "title": "GB wind forecast evaluation at day-ahead decision time",
            "unit": UNIT, "error_convention": ERR,
            "sources": {
                "actuals": {"dataset": "FUELHH", "filter": "fuelType=WIND", "time_field": "startTime",
                            "value_field": "generation"},
                "forecasts": {"dataset": "WINDFOR", "time_field": "startTime", "publish_field": "publishTime",
                              "value_field": "generation"},
                "base_url": settings.elexon_base_url,
                "attribution": "Contains BMRS data © Elexon Limited copyright and database right "
                               f"{date.today().year}. Source: Elexon Insights Solution (BMRS).",
            },
            "decision_window": {"first_decision_date": settings.decision_date_start.isoformat(),
                                "last_decision_date": settings.decision_date_end.isoformat(),
                                "delivery_from": settings.delivery_start.isoformat(),
                                "delivery_to": settings.delivery_end.isoformat()},
            "cutoff_rule": {
                "default_local": settings.default_cutoff.strftime("%H:%M"), "timezone": settings.market_tz,
                "lead_days": settings.decision_lead_days,
                "status": "ASSUMPTION (configurable). Not an official market rule.",
                "description": f"Forecast must have publishTime <= {settings.default_cutoff.strftime('%H:%M')} "
                               f"{settings.market_tz} on the day before the delivery date."},
            "data": {"state": store.state, "last_error": store.last_error,
                     "last_refresh_utc": d.fetched_at.isoformat() if d else None,
                     "report": d.report if d else None},
            "mape_note": f"MAPE excludes actuals < {settings.mape_min_actual_mw:g} MW; unstable near zero.",
        }

    @app.get("/api/v1/metrics", response_model=MetricsResponse, tags=["analysis"])
    def metrics(cutoff: str | None = None, date_from: date | None = None, date_to: date | None = None):
        df, c = get_df(cutoff, date_from, date_to)
        return MetricsResponse(cutoff_local=c.strftime("%H:%M"),
                               date_from=df["delivery_date"].min() if len(df) else "",
                               date_to=df["delivery_date"].max() if len(df) else "", unit=UNIT,
                               error_convention=ERR, metrics=A.compute_metrics(df, settings.mape_min_actual_mw))

    @app.get("/api/v1/time-series", response_model=TimeSeriesResponse, tags=["analysis"])
    def time_series(cutoff: str | None = None, date_from: date | None = None, date_to: date | None = None):
        df, c = get_df(cutoff, date_from, date_to)
        pts = [dict(start_utc=iso(r.start_utc), actual_mw=num(r.actual_mw), forecast_mw=num(r.forecast_mw),
                    error_mw=num(r.error_mw), publish_utc=iso(r.publish_utc), status=r.status)
               for r in df.itertuples()]
        return TimeSeriesResponse(cutoff_local=c.strftime("%H:%M"), unit=UNIT, count=len(pts), points=pts)

    @app.get("/api/v1/forecast-analysis", response_model=ForecastAnalysis, tags=["analysis"])
    def forecast_analysis(cutoff: str | None = None, date_from: date | None = None, date_to: date | None = None):
        df, c = get_df(cutoff, date_from, date_to)
        m = A.compute_metrics(df, settings.mape_min_actual_mw)
        daily = A.daily_metrics(df)
        tod = A.time_of_day_metrics(df, settings.market_tz)
        hind = A.hindsight_comparison(df)
        matched = df[df["status"] == A.STATUS_MATCHED]
        top = matched.nlargest(10, "abs_error_mw")
        return ForecastAnalysis(
            cutoff_local=c.strftime("%H:%M"), unit=UNIT, metrics=m, daily=daily, time_of_day=tod,
            histogram=A.error_histogram(df),
            scatter=[dict(start_utc=iso(r.start_utc), actual_mw=r.actual_mw, forecast_mw=r.forecast_mw)
                     for r in matched.itertuples()],
            largest_errors=[dict(start_utc=iso(r.start_utc), actual_mw=r.actual_mw, forecast_mw=r.forecast_mw,
                                 error_mw=r.error_mw, publish_utc=iso(r.publish_utc)) for r in top.itertuples()],
            insights=build_insights(m, daily, df, tod, hind), hindsight_comparison=hind)

    SORTS = {"start_utc", "forecast_mw", "actual_mw", "error_mw", "abs_error_mw", "publish_utc", "status"}

    @app.get("/api/v1/delivery-periods", response_model=DeliveryPeriodsResponse, tags=["analysis"])
    def delivery_periods(cutoff: str | None = None, date_from: date | None = None, date_to: date | None = None,
                         search: str | None = Query(None, max_length=50),
                         status: Literal["matched", "no_eligible_forecast", "no_actual",
                                         "no_forecast_and_no_actual"] | None = None,
                         sort_by: str = "start_utc", sort_dir: Literal["asc", "desc"] = "asc",
                         page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        if sort_by not in SORTS:
            raise HTTPException(422, f"sort_by must be one of {sorted(SORTS)}")
        df, c = get_df(cutoff, date_from, date_to)
        if status:
            df = df[df["status"] == status]
        if search:
            s = search.lower()
            hay = df["start_utc"].dt.strftime("%Y-%m-%d %H:%M").str.lower() + " " + df["status"]
            df = df[hay.str.contains(re.escape(s))]
        df = df.sort_values(sort_by, ascending=sort_dir == "asc", na_position="last", kind="stable")
        total = len(df)
        page_df = df.iloc[(page - 1) * page_size: page * page_size]
        items = [dict(start_utc=iso(r.start_utc), start_local=pd.Timestamp(r.start_utc).tz_convert(settings.market_tz).isoformat(),
                      delivery_date=r.delivery_date, cutoff_utc=iso(r.cutoff_utc), publish_utc=iso(r.publish_utc),
                      horizon_h=num(r.horizon_h), forecast_mw=num(r.forecast_mw), actual_mw=num(r.actual_mw),
                      error_mw=num(r.error_mw), abs_error_mw=num(r.abs_error_mw), status=r.status,
                      only_after_cutoff=bool(r.only_after_cutoff), latest_publish_utc=iso(r.latest_publish_utc))
                 for r in page_df.itertuples()]
        return DeliveryPeriodsResponse(cutoff_local=c.strftime("%H:%M"), unit=UNIT, total=total, page=page,
                                       page_size=page_size, items=items)

    @app.get("/api/v1/delivery-periods/vintages", response_model=VintageResponse, tags=["analysis"])
    def vintages(start_utc: datetime, cutoff: str | None = None):
        if store.dataset is None:
            raise HTTPException(503, {"state": store.state})
        c = parse_cutoff(cutoff)
        ts = pd.Timestamp(start_utc if start_utc.tzinfo else start_utc.replace(tzinfo=A.UTC)).tz_convert("UTC")
        df = store.analysis(c)
        row = df[df["start_utc"] == ts]
        if row.empty:
            raise HTTPException(404, "start_utc is not a delivery period in the analysis window")
        r = row.iloc[0]
        fc = store.dataset.forecasts
        fc = fc[fc["start_utc"] == ts].sort_values("publish_utc")
        out = [dict(publish_utc=iso(v.publish_utc), publish_raw=v.publish_raw, forecast_mw=float(v.forecast_mw),
                    eligible=bool(v.publish_utc <= r.cutoff_utc),
                    selected=bool(pd.notna(r.publish_utc) and v.publish_utc == r.publish_utc),
                    minutes_before_cutoff=float((r.cutoff_utc - v.publish_utc).total_seconds() / 60))
               for v in fc.itertuples()]
        return VintageResponse(start_utc=iso(ts), cutoff_utc=iso(r.cutoff_utc),
                               cutoff_rule="eligible if publishTime <= cutoff_utc; latest eligible is selected",
                               vintages=out)

    @app.post("/api/v1/data/refresh", response_model=RefreshAck, status_code=202, tags=["system"],
              dependencies=[Depends(refresh_guard)])
    def refresh(bg: BackgroundTasks):
        if store.state == "loading":
            raise HTTPException(409, "A refresh is already running")
        store.state = "loading"
        bg.add_task(_run_refresh)
        return RefreshAck(accepted=True, message="Refresh started; poll /api/v1/metadata for status")

    def _run_refresh():
        store.state = "ready" if store.dataset else "empty"   # let refresh() acquire the lock cleanly
        store.refresh()

    app.state.store = store
    return app


app = create_app()
