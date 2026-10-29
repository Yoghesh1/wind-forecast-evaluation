"""TEST FIXTURES ONLY - synthetic data, never mixed with live Elexon data.

Layout per delivery day D (Jan 2 .. Feb 1 2026), every 30-min startTime:
  actual                       = 5000 + 10*k                      (k = half-hour index in the month)
  forecast published D-2 12:00 = actual + 400   (eligible, but older)
  forecast published D-1 08:30 = actual + 50    (eligible, LATEST eligible at a 09:00 cutoff)
  forecast published D-1 10:30 = actual + 5     (published AFTER the 09:00 cutoff -> must be ignored)
Expected decision-time stats at 09:00 cutoff: MAE = 50, RMSE = 50, bias = +50.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc


def z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_rows(first=date(2026, 1, 2), last=date(2026, 2, 1), noise_seed: int | None = None):
    rng = random.Random(noise_seed) if noise_seed is not None else None
    actuals, forecasts, k = [], [], 0
    d = first
    while d <= last:
        day0 = datetime(d.year, d.month, d.day, tzinfo=UTC)
        for i in range(48):
            start = day0 + timedelta(minutes=30 * i)
            a = 5000 + 10 * k
            if rng:
                a = max(0.0, 6000 + 3000 * rng.uniform(-1, 1))
            actuals.append({"dataset": "FUELHH", "fuelType": "WIND", "startTime": z(start),
                            "settlementDate": d.isoformat(), "settlementPeriod": i + 1, "generation": a})
            prev = day0 - timedelta(days=1)
            for pub, off in ((prev - timedelta(days=1) + timedelta(hours=12), 400),
                             (prev + timedelta(hours=8, minutes=30), 50),
                             (prev + timedelta(hours=10, minutes=30), 5)):
                f = a + off + (rng.uniform(-500, 500) if rng else 0)
                forecasts.append({"dataset": "WINDFOR", "publishTime": z(pub), "startTime": z(start),
                                  "generation": f})
            k += 1
        d += timedelta(days=1)
    return actuals, forecasts
