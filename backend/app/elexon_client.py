"""Elexon Insights API access layer.

Contract (Elexon developer portal / BMRS docs; see README "Data sources"):
  * Base URL https://data.elexon.co.uk/bmrs/api/v1, public, no API key.
  * Stream endpoints return the complete result for the filter as JSON with no
    pagination (the portal states they have no limits on data return). We still
    request bounded windows and accept both a bare array and a {"data": [...]} envelope.
  * FUELHH/stream filters: settlementDateFrom / settlementDateTo (YYYY-MM-DD), fuelType.
  * WINDFOR/stream filters: publishDateTimeFrom / publishDateTimeTo only. There is no
    filter by delivery (start) time, so windows are over PUBLICATION time.
Window-boundary inclusivity is not documented, so windows touch/overlap and
duplicates are removed downstream.
"""
from __future__ import annotations

import logging
import time as _time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import httpx

log = logging.getLogger(__name__)
RETRY_STATUS = {429, 500, 502, 503, 504}


class ElexonError(Exception):
    """Raised when upstream data cannot be retrieved or has an unexpected shape."""


class _Transient(ElexonError):
    pass


class ElexonClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 30,
        max_retries: int = 4,
        backoff_base_s: float = 1.5,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = _time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self._http = http or httpx.Client(timeout=timeout_s)
        self._sleep = sleep

    def _get_rows(self, path: str, params: dict[str, Any]) -> list[dict]:
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                try:
                    resp = self._http.get(url, params=params, headers={"Accept": "application/json"})
                except httpx.TransportError as exc:  # timeouts, connection errors
                    raise _Transient(f"{type(exc).__name__}: {exc}") from exc
                if resp.status_code in RETRY_STATUS:
                    raise _Transient(f"HTTP {resp.status_code} from {path}")
                if resp.status_code >= 400:
                    raise ElexonError(f"HTTP {resp.status_code} from {path}: {resp.text[:200]}")
                return self._parse(resp, path)
            except _Transient as exc:
                last = exc
                if attempt == self.max_retries:
                    break
                delay = self.backoff_base_s * (2**attempt)
                log.warning("Transient failure (%s); retry %d in %.1fs", exc, attempt + 1, delay)
                self._sleep(delay)
        raise ElexonError(f"Upstream request failed after retries: {path} {params}: {last}") from last

    @staticmethod
    def _parse(resp: httpx.Response, path: str) -> list[dict]:
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ElexonError(f"Non-JSON response from {path}") from exc
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            payload = payload["data"]
        if not isinstance(payload, list):
            raise ElexonError(f"Unexpected payload shape from {path}: {type(payload).__name__}")
        return payload

    def fetch_actual_wind(self, d_from: date, d_to: date, window_days: int = 7) -> list[dict]:
        """FUELHH wind rows for settlement dates d_from..d_to (inclusive), in bounded windows."""
        rows: list[dict] = []
        cur = d_from
        while cur <= d_to:
            end = min(cur + timedelta(days=window_days - 1), d_to)
            rows += self._get_rows(
                "/datasets/FUELHH/stream",
                {"settlementDateFrom": cur.isoformat(), "settlementDateTo": end.isoformat(), "fuelType": "WIND"},
            )
            cur = end + timedelta(days=1)
        return rows

    def fetch_wind_forecasts(self, pub_from: datetime, pub_to: datetime, window_days: int = 2) -> list[dict]:
        """WINDFOR rows published in [pub_from, pub_to], in bounded UTC windows."""
        if pub_from.tzinfo is None or pub_to.tzinfo is None:
            raise ValueError("publish window must be timezone-aware")
        rows: list[dict] = []
        cur = pub_from.astimezone(timezone.utc)
        stop = pub_to.astimezone(timezone.utc)
        while cur < stop:
            end = min(cur + timedelta(days=window_days), stop)
            rows += self._get_rows(
                "/datasets/WINDFOR/stream",
                {"publishDateTimeFrom": cur.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "publishDateTimeTo": end.strftime("%Y-%m-%dT%H:%M:%SZ")},
            )
            cur = end
        return rows
