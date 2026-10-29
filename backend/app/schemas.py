from __future__ import annotations

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    data_state: str


class Metrics(BaseModel):
    eligible_periods: int
    matched_observations: int
    coverage_pct: float | None
    missing_forecast: int
    missing_actual: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    mape_pct: float | None
    mape_observations: int
    mape_excluded: int
    mape_min_actual_mw: float


class MetricsResponse(BaseModel):
    cutoff_local: str
    date_from: str
    date_to: str
    unit: str
    error_convention: str
    metrics: Metrics


class SeriesPoint(BaseModel):
    start_utc: str
    actual_mw: float | None
    forecast_mw: float | None
    error_mw: float | None
    publish_utc: str | None
    status: str


class TimeSeriesResponse(BaseModel):
    cutoff_local: str
    unit: str
    count: int
    points: list[SeriesPoint]


class DeliveryPeriod(BaseModel):
    start_utc: str
    start_local: str
    delivery_date: str
    cutoff_utc: str
    publish_utc: str | None
    horizon_h: float | None
    forecast_mw: float | None
    actual_mw: float | None
    error_mw: float | None
    abs_error_mw: float | None
    status: str
    only_after_cutoff: bool
    latest_publish_utc: str | None


class DeliveryPeriodsResponse(BaseModel):
    cutoff_local: str
    unit: str
    total: int
    page: int
    page_size: int
    items: list[DeliveryPeriod]


class Vintage(BaseModel):
    publish_utc: str
    publish_raw: str
    forecast_mw: float
    eligible: bool
    selected: bool
    minutes_before_cutoff: float


class VintageResponse(BaseModel):
    start_utc: str
    cutoff_utc: str
    cutoff_rule: str
    vintages: list[Vintage]


class Insight(BaseModel):
    id: str
    text: str
    sample_size: int


class ForecastAnalysis(BaseModel):
    cutoff_local: str
    unit: str
    metrics: Metrics
    daily: list[dict]
    time_of_day: list[dict]
    histogram: list[dict]
    scatter: list[dict]
    largest_errors: list[dict]
    insights: list[Insight]
    hindsight_comparison: dict


class RefreshAck(BaseModel):
    accepted: bool
    message: str
