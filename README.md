# Wind Forecast Decision Desk

A day-ahead wind generation forecast evaluation dashboard for UK electricity procurement decisions.

**Live application:** https://gridbricks-wind-forecast-2kyjv8aeg-yogheshrv-gmailcoms-projects.vercel.app/

**Backend health check:** https://gridbricks-wind-forecast-c9ft.onrender.com/api/v1/health

**Source code:** https://github.com/Yoghesh1/gridbricks-wind-forecast

---

## Overview

Wind generation is weather-dependent, so electricity procurement teams need to understand how much wind power is expected to be available before making day-ahead purchasing decisions.

The Wind Forecast Decision Desk helps users evaluate national-level UK wind generation forecasts against actual generation data from Elexon. It provides forecast error metrics, time-series visualisations, and delivery-period analysis to help users understand forecast accuracy and its potential implications for procurement decisions.

This application was developed as a pilot solution for the Gridbricks hiring challenge.

## Key Features

- **Forecast accuracy metrics:** Mean Absolute Error (MAE), Root Mean Squared Error (RMSE), forecast bias, and Mean Absolute Percentage Error (MAPE).
- **Actual versus forecast analysis:** Compare forecast wind generation with actual generation over the selected delivery period.
- **Time-series visualisation:** Explore how forecast and actual generation vary over time.
- **Daily performance analysis:** Examine forecast accuracy across individual days.
- **Error distribution and scatter analysis:** Understand forecast error patterns and the relationship between forecast and actual values.
- **Largest forecast errors:** Identify delivery periods with substantial differences between forecast and actual generation.
- **Delivery-period explorer:** Inspect individual periods, forecast publication times, actual generation, and forecast errors.
- **Configurable decision cutoff:** Select a publication-time cutoff for evaluating which forecasts were available before a delivery day.
- **Data refresh:** Refresh the data used by the dashboard.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, Vite |
| Backend | Python, FastAPI |
| Data source | Elexon BMRS API |
| Data processing | Pandas, NumPy |
| API communication | HTTP / JSON |
| Containerisation | Docker, Docker Compose |
| Frontend deployment | Vercel |
| Backend deployment | Render |
| Version control | Git, GitHub |

## Data Sources

The application uses national-level wind generation data from Elexon BMRS.

### Actual generation

Dataset: `FUELHH`

Only records with `fuelType = WIND` are considered.

Relevant fields:

- `startTime`: Delivery period start time.
- `generation`: Actual wind generation.

Official documentation: https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream

### Forecast generation

Dataset: `WINDFOR`

Relevant fields:

- `startTime`: Forecast target delivery time.
- `publishTime`: Time at which the forecast was published.
- `generation`: Forecast wind generation.

Official documentation: https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream

### Evaluation period

The analysis covers purchasing decisions made during January 2026, with delivery periods extending from January 2 through February 1, 2026, according to the application's configured date range.

## Forecast Selection and Evaluation Methodology

The application selects forecasts based on their publication time relative to a configurable day-ahead decision cutoff.

The current default cutoff is **09:00 Europe/London on the day before delivery**.

This cutoff is an explicit modelling assumption for the challenge. It should not be interpreted as an official market rule.

Forecasts are compared with actual generation for matching delivery periods. Forecast error is calculated as:

`Forecast Error = Forecast Generation − Actual Generation`

The dashboard reports:

- **MAE:** Average absolute forecast error.
- **RMSE:** Square root of the average squared forecast error, giving greater weight to larger errors.
- **Bias:** Average signed forecast error. Positive bias indicates overforecasting under the formula above.
- **MAPE:** Mean absolute percentage error, subject to the application's low-actual-value exclusion threshold.

### Data resolution limitation

The current dataset inspection identifies 1,488 half-hourly actual delivery periods and 744 distinct hourly forecast delivery periods in the evaluation window.

Consequently, not every half-hourly actual period has a matching forecast record. Unmatched periods are identified and excluded from matched-period error metrics rather than being filled with duplicated or interpolated forecast values.

This limits forecast coverage to approximately 50% of the half-hourly evaluation periods. The dashboard displays this limitation explicitly. The forecast data's temporal semantics should be verified against the source documentation before making operational decisions.

## Architecture

```text
                   User / Browser
                         |
                         v
              React + Vite Frontend
                    (Vercel)
                         |
                    HTTP / JSON
                         |
                         v
                 FastAPI Backend
                    (Render)
                         |
                         v
                  Elexon BMRS API
                    /        \
                   v          v
             FUELHH Actuals  WINDFOR Forecasts
                   \          /
                    v        v
                Data Processing
                         |
                         v
             Forecast Evaluation Metrics
                         |
                         v
              Dashboard API Responses
```

The frontend presents the analysis and requests data from the backend. The Python backend retrieves and processes the relevant actual and forecast datasets, applies the configured evaluation logic, and exposes API endpoints for the dashboard.

## Repository Structure

```text
gridbricks-wind-forecast/
├── backend/
│   ├── app/
│   │   └── ...                 # FastAPI application and analysis logic
│   ├── Dockerfile              # Backend container configuration
│   └── requirements.txt        # Python dependencies
├── frontend/
│   ├── src/                    # React application source
│   ├── public/                 # Static frontend assets
│   ├── package.json            # Frontend dependencies and scripts
│   └── ...                     # Vite and frontend configuration
├── docs/                       # Project documentation
├── .dockerignore               # Docker build exclusions
├── .gitignore                  # Git exclusions
├── docker-compose.yml          # Local multi-service setup
├── render.yaml                 # Render deployment configuration
└── README.md
```

The tree highlights the principal project components; individual source files and configuration files may vary as the project evolves.

## Getting Started

### Prerequisites

Install the following:

- Git
- Docker Desktop with Docker Compose
- A modern web browser

Alternatively, for development without Docker, install a compatible Python version and Node.js version supported by the frontend dependencies.

### 1. Clone the repository

```bash
git clone https://github.com/Yoghesh1/gridbricks-wind-forecast.git
cd gridbricks-wind-forecast
```

### 2. Start the application using Docker

From the repository root, run:

```bash
docker compose up --build
```

Wait for both services to finish starting.

Open the application:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Backend health endpoint: http://localhost:8000/api/v1/health

To stop the services, press `Ctrl+C`. To stop and remove the containers, run:

```bash
docker compose down
```

### 3. Run without Docker (optional)

Start the backend in one terminal:

```bash
cd backend
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in a separate terminal:

```bash
cd frontend
npm install
```

Configure the frontend API base URL using the environment variable described below, then run:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

If your backend entry point differs from `app.main:app`, use the module path defined by the repository's actual FastAPI application.

## Environment Configuration

### Frontend

Set `VITE_API_URL` to the backend API base URL.

Example local configuration in `frontend/.env.local`:

```env
VITE_API_URL=http://localhost:8000
```

For the deployed frontend, the configured value is:

```env
VITE_API_URL=https://gridbricks-wind-forecast-c9ft.onrender.com
```

Set this variable in the frontend hosting provider's environment settings and redeploy after changing it. Vite environment variables prefixed with `VITE_` are exposed to browser-side code, so never store secrets in them.

### Backend

Configure the backend's CORS origins to include the frontend origin that is actually being used.

Example origin:

```text
https://gridbricks-wind-forecast-2kyjv8aeg-yogheshrv-gmailcoms-projects.vercel.app
```

Use the format expected by the backend configuration, preserve any other required origins, and do not include URL paths in CORS origins.

Do not commit real environment files, credentials, or secrets to the repository.

## Deployment

### Frontend — Vercel

The React frontend is deployed on Vercel.

https://gridbricks-wind-forecast-2kyjv8aeg-yogheshrv-gmailcoms-projects.vercel.app/

Deployment configuration:

- Root directory: `frontend`
- Framework preset: Vite
- Build command: `npm run build`
- Output directory: `dist`
- Environment variable: `VITE_API_URL`

### Backend — Render

The FastAPI backend is deployed on Render.

- Backend base URL: https://gridbricks-wind-forecast-c9ft.onrender.com
- Health endpoint: https://gridbricks-wind-forecast-c9ft.onrender.com/api/v1/health

The root URL may return `404 Not Found` if no root route is defined. Use the health endpoint to check service availability.

## Testing and Validation

The application was exercised locally with Docker Compose, and deployed API requests were observed returning HTTP `200 OK`.

Before relying on a new deployment, verify:

1. The backend health endpoint responds successfully.
2. The frontend loads data from the configured backend.
3. Forecast and actual charts render.
4. Delivery-period records are displayed.
5. Data refresh completes successfully.
6. Browser developer tools show no unresolved API or CORS errors.

## Limitations and Assumptions

- The evaluation is restricted to national-level wind generation from Elexon.
- The default decision cutoff is a configurable modelling assumption, not an official market rule.
- The hourly forecast and half-hourly actual data resolutions result in unmatched delivery periods.
- Unmatched periods are excluded from matched-period error metrics rather than artificially filled.
- MAPE is sensitive to small actual generation values; the implementation excludes values below its configured threshold.
- Forecast accuracy metrics describe historical performance and do not guarantee future forecast accuracy or determine the optimal procurement volume.
- The application is a challenge prototype, not a production electricity-trading system.

## AI Tools and Development Assistance
AI-assisted development tools were used during implementation, debugging, testing, and documentation. Generated suggestions and code changes were reviewed and validated as part of the development workflow.

Acknowledgements

Elexon BMRS for providing the actual and forecast generation datasets.

Gridbricks for the hiring challenge and problem statement.

License

No license has been specified for this repository. Unless a license is added, reuse and redistribution are subject to the applicable default copyright rules.
