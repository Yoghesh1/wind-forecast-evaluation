"""LOCAL FAKE of the two Elexon stream endpoints, for tests and offline development ONLY.
Run: uvicorn tests.fake_elexon:app --port 9100  and set ELEXON_BASE_URL=http://localhost:9100
Data is synthetic (see fixtures.py) and must never be presented as real Elexon data."""
from fastapi import FastAPI

from .fixtures import make_rows

app = FastAPI(title="FAKE Elexon (test fixture)")
_A, _F = make_rows(noise_seed=42)


@app.get("/datasets/FUELHH/stream")
def fuelhh(settlementDateFrom: str, settlementDateTo: str, fuelType: str | None = None):
    return [r for r in _A if settlementDateFrom <= r["settlementDate"] <= settlementDateTo]


@app.get("/datasets/WINDFOR/stream")
def windfor(publishDateTimeFrom: str, publishDateTimeTo: str):
    return [r for r in _F if publishDateTimeFrom <= r["publishTime"] <= publishDateTimeTo]
