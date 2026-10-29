# Demo scripts (video total ≤ 10 min, unlisted on YouTube)

Record against the **deployed app with real Elexon data**, not the fake server. Check the numbers on screen once before recording.

## Part 1 – Client pitch (≤ 5:00)
| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Dashboard header | Day-ahead buying means committing before the delivery day. The question is not "what is the latest forecast" but "what forecast did we actually have when we decided, and how reliable was it?" |
| 0:30–1:15 | Cutoff control + assumption note | For every half-hour of delivery, the tool picks the latest wind forecast published at or before the decision cutoff (default 09:00 London, day before). It is configurable; we'd confirm your real gate time. |
| 1:15–2:15 | KPI cards | MAE, RMSE, bias, coverage and MAPE, each with units, definition and sample size. Read the *actual* values on screen. Explain the sign: positive = forecast higher than reality. |
| 2:15–3:15 | Forecast vs actual chart; zoom with slider; hover | Show a large-miss day. Hover: actual, forecast, error, and when the forecast was published. |
| 3:15–4:00 | Insights + daily/bias charts | Read the generated insights (computed, not hand-written): worst day, systematic bias, coverage gaps. |
| 4:00–4:40 | Explorer: sort by |error|, click a row → vintages | Show which forecast versions existed, which were too late, and which was used. |
| 4:40–5:00 | Close | Error figures can inform how much buffer to plan for. We do not compute demand, shortfall or optimal volume, as no demand/price/thermal data was in scope. Next: add those inputs. |

## Part 2 – Technical review (≤ 5:00)
| Time | Show | Say |
|---|---|---|
| 0:00–0:40 | README architecture diagram / repo tree | React+Vite+Recharts → FastAPI → in-memory/disk cache ← Elexon client. Dashboard never hits Elexon. |
| 0:40–1:40 | `elexon_client.py`, `normalize.py` | Bounded windows, retries with exponential backoff for 429/5xx/timeouts only, no retry on 4xx, both response envelopes handled, UTC normalisation with raw strings preserved, deterministic de-dupe with conflict counts. Failure never falls back to fake data. |
| 1:40–2:50 | `analysis.py` `build_analysis` | As-of backward join of cutoff against publishTime per startTime: one forecast per period, no many-to-many, no look-ahead. Hindsight view exists only to size the bias. DST-safe grid. |
| 2:50–3:30 | `compute_metrics` + `tests/test_metrics.py` | Known-value tests; MAPE threshold; unmatched rows excluded, not zero-filled. |
| 3:30–4:10 | Run `pytest` and `npm test` | Show real results. Mention tests use labelled synthetic fixtures. |
| 4:10–4:40 | Docker compose, `render.yaml`, `vercel.json`, env vars | One command locally; split deploy; CORS and API URL from env. |
| 4:40–5:00 | Limitations | Cutoff is an assumption; free-tier cold start re-downloads; single-process cache. |

## Submission checklist
- [ ] Public GitHub repo with anonymous name (e.g. `kx7q2`); no `.env`, keys, or personal info; author metadata/commit email anonymised
- [ ] README has file/directory descriptions, start instructions, and the live Vercel link
- [ ] Backend deployed (Render) and `/api/v1/health` returns ok
- [ ] Frontend deployed (Vercel) with `VITE_API_URL` = backend URL; backend `CORS_ORIGINS` = Vercel URL
- [ ] Deployed app shows real January 2026 data (check banners for partial-data warnings)
- [ ] Video ≤ 10 min, both parts, uploaded as **Unlisted** on YouTube
- [ ] Open repo, app URL and video in an incognito window and confirm access
- [ ] Submit all URLs in the Microsoft form: https://forms.cloud.microsoft/r/FTX6K2bbnU
