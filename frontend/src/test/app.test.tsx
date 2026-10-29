import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import App from "../App";

const baseMd = {
  unit: "MW", error_convention: "error = forecast - actual",
  sources: { base_url: "x", attribution: "Contains BMRS data © Elexon Limited" },
  decision_window: { first_decision_date: "2026-01-01", last_decision_date: "2026-01-31", delivery_from: "2026-01-02", delivery_to: "2026-02-01" },
  cutoff_rule: { default_local: "09:00", timezone: "Europe/London", lead_days: 1, status: "ASSUMPTION", description: "rule" },
  data: { state: "ready", last_error: null, last_refresh_utc: "2026-10-28T10:00:00+00:00", report: { warnings: [] } },
  mape_note: "MAPE note",
};
const emptyMetrics = { eligible_periods: 10, matched_observations: 0, coverage_pct: 0, missing_forecast: 10, missing_actual: 0,
  mae_mw: null, rmse_mw: null, bias_mw: null, mape_pct: null, mape_observations: 0, mape_excluded: 0, mape_min_actual_mw: 100 };

function mockFetch(routes: Record<string, unknown | (() => Response)>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    const r = routes[path];
    if (r === undefined) return new Response(JSON.stringify({ detail: "nf" }), { status: 404 });
    return typeof r === "function" ? (r as () => Response)() : new Response(JSON.stringify(r), { status: 200 });
  }));
}
afterEach(() => vi.unstubAllGlobals());

test("shows connecting then an error when the API is unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
  render(<App />);
  expect(screen.getByText(/Connecting to API/)).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the API/);
});

test("shows a loading banner while the backend downloads", async () => {
  mockFetch({ "/api/v1/metadata": { ...baseMd, data: { state: "loading", last_error: null, last_refresh_utc: null, report: null } } });
  render(<App />);
  expect(await screen.findByText(/Downloading Elexon data/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Refreshing/ })).toBeDisabled();
});

test("shows upstream failure without substitute data", async () => {
  mockFetch({ "/api/v1/metadata": { ...baseMd, data: { state: "error", last_error: "HTTP 503", last_refresh_utc: null, report: null } } });
  render(<App />);
  expect(await screen.findByText(/No substitute data is shown/)).toBeInTheDocument();
});

test("shows empty state and partial-data warning when nothing matches", async () => {
  mockFetch({
    "/api/v1/metadata": { ...baseMd, data: { ...baseMd.data, report: { warnings: ["forecasts: 0 distinct delivery periods"] } } },
    "/api/v1/forecast-analysis": { metrics: emptyMetrics, daily: [], time_of_day: [], histogram: [], scatter: [], largest_errors: [], insights: [],
      hindsight_comparison: { observations: 0, decision_time_mae_mw: null, latest_available_mae_mw: null } },
    "/api/v1/time-series": { points: [] },
    "/api/v1/delivery-periods": { total: 0, page: 1, page_size: 20, items: [] },
  });
  render(<App />);
  expect(await screen.findByText(/Partial data/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText(/No matched forecast\/actual periods/)).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText(/No delivery periods match/)).toBeInTheDocument());
});
