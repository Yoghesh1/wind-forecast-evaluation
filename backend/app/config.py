"""Environment-based configuration. No secrets are logged or exposed via the API."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, time, timedelta
from functools import lru_cache
from pathlib import Path


def _hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Settings:
    elexon_base_url: str
    request_timeout_s: float
    max_retries: int
    backoff_base_s: float
    cors_origins: list[str]
    cache_path: Path
    decision_date_start: date      # first purchasing-decision date (inclusive)
    decision_date_end: date        # last purchasing-decision date (inclusive)
    decision_lead_days: int        # delivery day = decision date + lead (day-ahead => 1)
    default_cutoff: time           # BUSINESS ASSUMPTION, local market time, on the decision date
    market_tz: str
    mape_min_actual_mw: float      # actuals below this are excluded from MAPE
    forecast_lookback_days: int    # how far before the first delivery day to fetch forecasts
    refresh_token: str | None
    auto_refresh_on_start: bool

    @property
    def delivery_start(self) -> date:
        return self.decision_date_start + timedelta(days=self.decision_lead_days)

    @property
    def delivery_end(self) -> date:
        return self.decision_date_end + timedelta(days=self.decision_lead_days)


@lru_cache
def get_settings() -> Settings:
    e = os.environ.get
    return Settings(
        elexon_base_url=e("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1").rstrip("/"),
        request_timeout_s=float(e("ELEXON_TIMEOUT_S", "30")),
        max_retries=int(e("ELEXON_MAX_RETRIES", "4")),
        backoff_base_s=float(e("ELEXON_BACKOFF_BASE_S", "1.5")),
        cors_origins=[o.strip() for o in e("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
        cache_path=Path(e("CACHE_PATH", "data/elexon_cache.json")),
        decision_date_start=date.fromisoformat(e("DECISION_DATE_START", "2026-01-01")),
        decision_date_end=date.fromisoformat(e("DECISION_DATE_END", "2026-01-31")),
        decision_lead_days=int(e("DECISION_LEAD_DAYS", "1")),
        default_cutoff=_hhmm(e("DEFAULT_CUTOFF", "09:00")),
        market_tz=e("MARKET_TZ", "Europe/London"),
        mape_min_actual_mw=float(e("MAPE_MIN_ACTUAL_MW", "100")),
        forecast_lookback_days=int(e("FORECAST_LOOKBACK_DAYS", "3")),
        refresh_token=e("REFRESH_TOKEN") or None,
        auto_refresh_on_start=e("AUTO_REFRESH_ON_START", "true").lower() == "true",
    )
