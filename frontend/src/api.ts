export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface Metrics {
  eligible_periods: number; matched_observations: number; coverage_pct: number | null;
  missing_forecast: number; missing_actual: number;
  mae_mw: number | null; rmse_mw: number | null; bias_mw: number | null;
  mape_pct: number | null; mape_observations: number; mape_excluded: number; mape_min_actual_mw: number;
}
export interface Metadata {
  unit: string; error_convention: string;
  sources: { base_url: string; attribution: string };
  decision_window: { first_decision_date: string; last_decision_date: string; delivery_from: string; delivery_to: string };
  cutoff_rule: { default_local: string; timezone: string; lead_days: number; status: string; description: string };
  data: { state: "empty" | "loading" | "ready" | "error"; last_error: string | null; last_refresh_utc: string | null;
          report: { warnings: string[] } | null };
  mape_note: string;
}
export interface SeriesPoint { start_utc: string; actual_mw: number | null; forecast_mw: number | null;
  error_mw: number | null; publish_utc: string | null; status: string }
export interface Daily { date: string; eligible_periods: number; matched_observations: number; coverage_pct: number;
  mae_mw: number | null; rmse_mw: number | null; bias_mw: number | null }
export interface Analysis {
  metrics: Metrics; daily: Daily[]; time_of_day: { slot: string; mae_mw: number; bias_mw: number; matched_observations: number }[];
  histogram: { from_mw: number; to_mw: number; count: number }[];
  scatter: { start_utc: string; actual_mw: number; forecast_mw: number }[];
  largest_errors: { start_utc: string; actual_mw: number; forecast_mw: number; error_mw: number; publish_utc: string }[];
  insights: { id: string; text: string; sample_size: number }[];
  hindsight_comparison: { observations: number; decision_time_mae_mw: number | null; latest_available_mae_mw: number | null };
}
export interface Period {
  start_utc: string; delivery_date: string; cutoff_utc: string; publish_utc: string | null; horizon_h: number | null;
  forecast_mw: number | null; actual_mw: number | null; error_mw: number | null; abs_error_mw: number | null;
  status: string; only_after_cutoff: boolean; latest_publish_utc: string | null;
}
export interface PeriodsPage { total: number; page: number; page_size: number; items: Period[] }
export interface Vintages { start_utc: string; cutoff_utc: string; cutoff_rule: string;
  vintages: { publish_utc: string; forecast_mw: number; eligible: boolean; selected: boolean; minutes_before_cutoff: number }[] }

export class ApiError extends Error {
  constructor(message: string, public status?: number) { super(message); }
}

export async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") q.set(k, String(v)); });
  let res: Response;
  try { res = await fetch(`${API_URL}${path}?${q}`); }
  catch { throw new ApiError(`Cannot reach the API at ${API_URL}. Is the backend running?`); }
  if (!res.ok) {
    let detail = `${res.status}`;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : j.detail?.message ?? JSON.stringify(j.detail); } catch { /* keep status */ }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export async function refreshData(token?: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/v1/data/refresh`, { method: "POST", headers: token ? { "X-Refresh-Token": token } : {} });
  if (!res.ok) throw new ApiError(res.status === 401 ? "Refresh requires a valid token" : `Refresh failed (${res.status})`, res.status);
}

export const fmtMW = (v: number | null | undefined, signed = false) =>
  v == null ? "—" : `${signed && v > 0 ? "+" : ""}${v.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
export const fmtTs = (iso: string | null) => (iso ? iso.replace("T", " ").slice(0, 16) + " UTC" : "—");
