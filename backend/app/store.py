"""In-memory + on-disk cache of normalised Elexon data. The dashboard never calls Elexon directly."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from .analysis import build_analysis
from .config import Settings
from .elexon_client import ElexonClient, ElexonError
from .normalize import normalize_actuals, normalize_forecasts

log = logging.getLogger(__name__)


def _native_resolution_min(starts: pd.Series) -> int | None:
    """Most common gap between consecutive distinct start times (robust to a few missing intervals)."""
    u = starts.drop_duplicates().sort_values()
    if len(u) < 2:
        return None
    gaps = (u.diff().dropna().dt.total_seconds() / 60).round().astype(int)
    return int(gaps.mode().iloc[0])


def coverage_report(act: pd.DataFrame, fc: pd.DataFrame, d_from, d_to, tz: str) -> dict:
    """Coverage diagnostics for the delivery window d_from..d_to (local dates, inclusive).

    Counts DISTINCT startTime instants (UTC) inside the window, so duplicate rows never inflate
    the count and DST days (46/50 half-hours) are handled by measuring the real UTC span.
    Each dataset is judged against ITS OWN native cadence, inferred from the data:
    a gap is only reported when instants are missing at that cadence. Separately, if the
    forecast cadence is coarser than 30 minutes, the half-hour periods without a forecast
    row are stated explicitly. They stay unmatched and are never interpolated or filled.
    """
    zone = ZoneInfo(tz)
    lo = datetime.combine(d_from, time(0), tzinfo=zone).astimezone(timezone.utc)
    hi = datetime.combine(d_to + timedelta(days=1), time(0), tzinfo=zone).astimezone(timezone.utc)
    span_min = (hi - lo).total_seconds() / 60
    half_hours = int(span_min // 30)
    warnings: list[str] = []
    info: dict = {"window_half_hour_periods": half_hours}
    for name, df in (("actuals", act), ("forecasts", fc)):
        if df.empty:
            warnings.append(f"Elexon returned no {name} rows for the requested window.")
            info[f"{name}_distinct_periods_in_window"] = 0
            continue
        win = df.loc[(df["start_utc"] >= lo) & (df["start_utc"] < hi), "start_utc"]
        have = int(win.nunique())
        res = _native_resolution_min(win) if have else None
        info[f"{name}_distinct_periods_in_window"] = have
        info[f"{name}_resolution_minutes"] = res
        info[f"{name}_start_minute_of_hour_counts"] = (
            {int(k): int(v) for k, v in win.drop_duplicates().dt.minute.value_counts().sort_index().items()})
        if have == 0:
            warnings.append(f"{name}: no rows with a delivery period inside {d_from}..{d_to}.")
            continue
        native_expected = int(span_min // res) if res else half_hours
        if have < native_expected:
            warnings.append(f"{name}: {have} distinct delivery periods in {d_from}..{d_to}; "
                            f"{native_expected} expected at the observed {res}-minute resolution "
                            f"(gap of {native_expected - have}).")
        if name == "forecasts" and res and res > 30:
            warnings.append(f"forecasts: Elexon supplies one forecast per {res} minutes "
                            f"({have} distinct delivery periods vs {half_hours} half-hour periods). "
                            f"The other {max(half_hours - have, 0)} half-hour periods have no forecast row, "
                            f"are shown as unmatched and are excluded from error metrics (not interpolated). "
                            f"Coverage is therefore capped near {100 * have / half_hours:.0f}%.")
    return {"warnings": warnings, "coverage": info}


@dataclass
class Dataset:
    actuals: pd.DataFrame
    forecasts: pd.DataFrame
    fetched_at: datetime
    report: dict
    version: int = 0


@dataclass
class DataStore:
    settings: Settings
    client: ElexonClient
    dataset: Dataset | None = None
    state: str = "empty"            # empty | loading | ready | error
    last_error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _cache: dict = field(default_factory=dict)

    # ------------------------------------------------------------ fetch
    def refresh(self) -> bool:
        """Blocking refresh. Returns False if one is already running. On failure the
        previous dataset (if any) is retained and the error is reported - never replaced by fake data."""
        if not self._lock.acquire(blocking=False):
            return False
        self.state = "loading"
        try:
            s = self.settings
            pub_from = datetime.combine(s.delivery_start - timedelta(days=s.forecast_lookback_days),
                                        time(0), tzinfo=timezone.utc)
            pub_to = datetime.combine(s.decision_date_end + timedelta(days=1), time(0), tzinfo=timezone.utc)
            raw_a = self.client.fetch_actual_wind(s.delivery_start - timedelta(days=1), s.delivery_end + timedelta(days=1))
            raw_f = self.client.fetch_wind_forecasts(pub_from, pub_to)
            act, a_stats = normalize_actuals(raw_a)
            fc, f_stats = normalize_forecasts(raw_f)
            now = datetime.now(timezone.utc)
            report = {"actuals": a_stats, "forecasts": f_stats,
                      "forecast_publish_window_utc": [pub_from.isoformat(), pub_to.isoformat()],
                      "actuals_range_utc": self._range(act, "start_utc"),
                      "forecast_delivery_range_utc": self._range(fc, "start_utc"),
                      "forecast_publish_range_utc": self._range(fc, "publish_utc"),
                      **coverage_report(act, fc, s.delivery_start, s.delivery_end, s.market_tz)}
            version = (self.dataset.version + 1) if self.dataset else 1
            self.dataset = Dataset(act, fc, now, report, version)
            self._cache.clear()
            self._save()
            self.state, self.last_error = "ready", None
            return True
        except (ElexonError, ValueError) as exc:
            log.error("Refresh failed: %s", exc)
            self.last_error = str(exc)
            self.state = "ready" if self.dataset else "error"   # keep previous good data, flag the error
            return True
        finally:
            self._lock.release()

    @staticmethod
    def _range(df: pd.DataFrame, col: str) -> list[str] | None:
        return None if df.empty else [df[col].min().isoformat(), df[col].max().isoformat()]

    # ------------------------------------------------------------ cache
    def _save(self) -> None:
        d = self.dataset
        if d is None:
            return
        path = self.settings.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": d.fetched_at.isoformat(), "report": d.report,
            "actuals": d.actuals.assign(start_utc=d.actuals["start_utc"].map(lambda t: t.isoformat())).to_dict("records"),
            "forecasts": d.forecasts.assign(
                start_utc=d.forecasts["start_utc"].map(lambda t: t.isoformat()),
                publish_utc=d.forecasts["publish_utc"].map(lambda t: t.isoformat())).to_dict("records"),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)

    def load_cache(self) -> bool:
        path = self.settings.cache_path
        if not path.exists():
            return False
        try:
            p = json.loads(path.read_text())
            act = pd.DataFrame(p["actuals"], columns=["start_utc", "start_raw", "actual_mw"])
            fc = pd.DataFrame(p["forecasts"], columns=["start_utc", "publish_utc", "start_raw", "publish_raw", "forecast_mw"])
            act["start_utc"] = pd.to_datetime(act["start_utc"], utc=True)
            fc["start_utc"] = pd.to_datetime(fc["start_utc"], utc=True)
            fc["publish_utc"] = pd.to_datetime(fc["publish_utc"], utc=True)
            cfg = self.settings
            report = {**p["report"], **coverage_report(act, fc, cfg.delivery_start, cfg.delivery_end, cfg.market_tz)}
            self.dataset = Dataset(act, fc, datetime.fromisoformat(p["fetched_at"]), report, 1)
            self.state = "ready"
            return True
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            log.error("Ignoring unreadable cache %s: %s", path, exc)
            return False

    # ------------------------------------------------------------ analysis
    def analysis(self, cutoff: time) -> pd.DataFrame:
        if self.dataset is None:
            raise LookupError("No data loaded")
        key = (self.dataset.version, cutoff)
        if key not in self._cache:
            s = self.settings
            self._cache[key] = build_analysis(self.dataset.actuals, self.dataset.forecasts,
                                              s.delivery_start, s.delivery_end, cutoff, s.market_tz,
                                              s.decision_lead_days)
        return self._cache[key]
