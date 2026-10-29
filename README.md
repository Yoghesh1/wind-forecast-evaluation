# Wind Forecast Decision Desk

A web app that shows, for each half-hour of GB national wind generation, **which Elexon forecast was available at the day-ahead purchasing decision** and **how far it was from actual generation**.

> **AI disclosure:** This project was built with the assistance of AI tools (Claude). All code, tests and documentation were generated or edited with AI help and should be reviewed as such.

## Business context
A UK utility buys power on the day-ahead market one day before delivery, so it relies on wind forecasts published *before* the decision. Scope is limited to national wind data from Elexon, for purchase decisions made in **January 2026**.
This app evaluates **forecast error only**. It does **not** compute demand, power shortfall, or an optimal purchase quantity: the brief supplies no demand, price or thermal data.

## Features
KPI cards (MAE, RMSE, bias, matched count/coverage, limited MAPE) · forecast-vs-actual chart with zoom and tooltips (incl. publish time) · daily MAE/RMSE/bias · error histogram · scatter with y=x line · MAE by time of day · top-10 errors · searchable/sortable/paginated delivery-period explorer · per-period forecast-vintage inspector · data-derived insights · configurable cutoff · refresh action · loading/empty/partial/error states.

## Architecture and data flow
```
Elexon Insights API ──► ElexonClient (bounded windows, retry/backoff)
                          └► normalize (UTC, validate, de-dupe)
                              └► DataStore (memory + JSON cache on disk)
                                  └► analysis (cutoff selection, metrics, insights)
                                      └► FastAPI /api/v1/*  ◄── React dashboard (Vite, Recharts)
```
The dashboard only talks to the backend cache. Elexon is called at startup (if no cache exists) and on "Refresh data".

## Repository layout
| Path | Purpose |
|---|---|
| `backend/app/config.py` | Env-based settings |
| `backend/app/elexon_client.py` | Upstream access, windows, retries |
| `backend/app/normalize.py` | Validation, UTC normalisation, de-duplication |
| `backend/app/analysis.py` | Cutoff, forecast selection, metrics |
| `backend/app/insights.py` | Deterministic insight text |
| `backend/app/store.py` | Cache + refresh orchestration |
| `backend/app/main.py`, `schemas.py` | REST routes and Pydantic schemas |
| `backend/tests/` | Pytest suite; `fixtures.py` / `fake_elexon.py` are **synthetic test fixtures** |
| `frontend/src/` | React + TypeScript dashboard and Vitest tests |
| `docker-compose.yml`, `*/Dockerfile` | Local containers |
| `render.yaml`, `frontend/vercel.json` | Deployment config |
| `docs/DEMO_SCRIPTS.md` | Two ≤5-min demo scripts + submission checklist |

## Elexon data sources
Base URL `https://data.elexon.co.uk/bmrs/api/v1` (public, no key). Documentation: `bmrs.elexon.co.uk/api-documentation` and `developer.data.elexon.co.uk`.
- **Actuals:** `GET /datasets/FUELHH/stream` with `settlementDateFrom/To` and `fuelType=WIND`; uses `startTime` and `generation`.
- **Forecasts:** `GET /datasets/WINDFOR/stream` with `publishDateTimeFrom/To`; uses `startTime`, `publishTime`, `generation`.
- Stream endpoints return the full result with no pagination (per the developer portal), so the client uses bounded windows (7 days for actuals, 2 days for forecasts) and tolerates a bare array or `{"data": [...]}`.
- WINDFOR can be filtered only by **publish** time, so forecasts are fetched from `FORECAST_LOOKBACK_DAYS` before the first delivery day.
- Timestamps are UTC (`Z`); original strings are kept alongside normalised ones. Units are MW (as documented for generation outturn; confirm on live data).

**Verification status:** the contract above was taken from Elexon documentation and developer-portal text. The development sandbox had no network route to Elexon, so **the client has not been run against the live API**. Do this first: `docker compose up`, then check the UI banners and `/api/v1/metadata → data.report`. Window-boundary inclusivity is undocumented, so windows overlap-safe de-duplication is used.

## Coverage reporting and forecast cadence
`/api/v1/metadata → data.report.coverage` lists, per dataset, distinct delivery instants in the window, the **observed cadence** (most common gap between start times) and a minute-of-hour histogram, so cadence can be checked against live data. Gaps are judged against each dataset's own cadence; duplicates never inflate counts; DST days use the real UTC span (46/50 half-hours).
If WINDFOR supplies one forecast per hour (a live report showed 744 distinct forecast periods for 31 days), the `:30` half-hour periods have **no forecast row**. They are shown as `no_eligible_forecast`, excluded from MAE/RMSE/bias, and **never interpolated or copied from the previous hour**. Coverage is then capped near 50% by construction, and the dashboard says so in a warning rather than hiding it.

## Decision window and cutoff (assumptions)
- Decisions are made on each day **1–31 Jan 2026**; the delivery day is the following day, so delivery covers **2 Jan – 1 Feb 2026**. Change `DECISION_DATE_*` if you read the brief differently.
- **Cutoff default: 09:00 Europe/London on the day before delivery.** This is an **assumption, not an official market rule**; the brief gives no time. Confirm with the client (the real auction gate-closure time) and set `DEFAULT_CUTOFF` or use the UI control.
- Selection: for each delivery `startTime`, choose the forecast row with the **latest `publishTime` ≤ cutoff** (as-of join; a forecast published exactly at the cutoff is eligible). Forecasts published later are never used. No interpolation or zero-filling.
- Duplicates: identical `(startTime, publishTime)` rows are collapsed, keeping the last in upstream order; conflicting values are counted in the refresh report.
- A **hindsight comparison** (newest forecast ever published) is reported only to size look-ahead bias and is labelled as invalid for evaluation.

## Metrics
Error = **forecast − actual** (MW); positive = over-forecast.
- **MAE** = mean(|e|). **RMSE** = √mean(e²). **Bias** = mean(e).
- **MAPE** = mean(|e|/actual)×100 over matched periods with actual ≥ `MAPE_MIN_ACTUAL_MW` (default 100 MW). It is undefined at zero and unstable near zero, so small actuals are excluded and counted.
- **Matched observations** = periods with both an eligible forecast and an actual. **Coverage** = matched ÷ all delivery periods in range.
- No confidence intervals or performance claims are made.

## API
Swagger UI at `/docs`. `GET /api/v1/health | metadata | metrics | time-series | forecast-analysis | delivery-periods | delivery-periods/vintages`, `POST /api/v1/data/refresh` (202; protected by `X-Refresh-Token` when `REFRESH_TOKEN` is set). Query params: `cutoff=HH:MM`, `date_from`, `date_to`.

## Run locally
Prerequisites: Python 3.11+, Node 20+, or Docker.
```bash
# Docker
cp .env.example .env
docker compose up --build        # UI http://localhost:5173  API http://localhost:8000/docs

# Without Docker
cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```
Offline development only (synthetic data, never for demos): `uvicorn tests.fake_elexon:app --port 9100` then `ELEXON_BASE_URL=http://localhost:9100 uvicorn app.main:app`.

## Tests and builds
```bash
cd backend && pytest                      # 59 tests
cd frontend && npm test && npm run typecheck && npm run build
```
Last run in the development sandbox: backend 59 passed; frontend 4 passed; `tsc --noEmit` clean; production build succeeded. Docker builds and the live Elexon download were **not** run there.

## Deployment
Backend → Render (`render.yaml`, Docker, free plan): create a Blueprint, set `CORS_ORIGINS` to the Vercel URL. Free plan has no persistent disk and sleeps, so data is re-downloaded after a cold start.
Frontend → Vercel: import repo, root `frontend`, set `VITE_API_URL` to the Render URL, deploy.
**Deployed URLs:** _not yet deployed; add here after verification._

## Known limitations / future work
Cutoff is assumed · live API not yet verified from this build environment · single-process cache (use a DB for multiple workers) · no demand/price data so no procurement quantity · charts show UTC times · bundle is not code-split.
