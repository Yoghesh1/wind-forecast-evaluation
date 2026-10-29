import { useCallback, useEffect, useState } from "react";
import { ApiError, get, refreshData, fmtTs } from "./api";
import type { Analysis, Metadata, SeriesPoint } from "./api";
import { Banner } from "./components/Banner";
import { Kpis } from "./components/Kpis";
import { SeriesChart } from "./components/SeriesChart";
import { ErrorCharts } from "./components/ErrorCharts";
import { PeriodExplorer } from "./components/PeriodExplorer";

export default function App() {
  const [md, setMd] = useState<Metadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState<string>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [busy, setBusy] = useState(false);

  const loadMeta = useCallback(async () => {
    try { setMd(await get<Metadata>("/api/v1/metadata")); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { loadMeta(); }, [loadMeta]);
  // Poll while the backend is downloading.
  useEffect(() => {
    if (md?.data.state !== "loading") return;
    const t = setInterval(loadMeta, 3000);
    return () => clearInterval(t);
  }, [md?.data.state, loadMeta]);
  useEffect(() => {
    if (md && !cutoff) { setCutoff(md.cutoff_rule.default_local); setDateFrom(md.decision_window.delivery_from); setDateTo(md.decision_window.delivery_to); }
  }, [md, cutoff]);

  const hasData = md?.data.last_refresh_utc != null;
  const refreshedAt = md?.data.last_refresh_utc;
  useEffect(() => {
    if (!hasData || !cutoff || !dateFrom || !dateTo) return;
    let live = true;
    const p = { cutoff, date_from: dateFrom, date_to: dateTo };
    Promise.all([get<Analysis>("/api/v1/forecast-analysis", p), get<{ points: SeriesPoint[] }>("/api/v1/time-series", p)])
      .then(([a, s]) => { if (live) { setAnalysis(a); setSeries(s.points); setError(null); } })
      .catch((e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [hasData, refreshedAt, cutoff, dateFrom, dateTo]);

  const doRefresh = async () => {
    setBusy(true);
    try { await refreshData(); await loadMeta(); } catch (e) { setError((e as ApiError).message); } finally { setBusy(false); }
  };

  const loading = md?.data.state === "loading";
  return (
    <div className="app">
      <header>
        <div>
          <h1>Wind Forecast Decision Desk</h1>
          <p>GB national wind: what forecast was available at the day-ahead decision, and how wrong was it?</p>
          {md && <p className="sub">Decisions {md.decision_window.first_decision_date} → {md.decision_window.last_decision_date} · delivery {md.decision_window.delivery_from} → {md.decision_window.delivery_to} · unit {md.unit}</p>}
        </div>
        <div className="actions">
          <button onClick={doRefresh} disabled={busy || loading}>{loading || busy ? "Refreshing…" : "Refresh data"}</button>
          <small>Last refresh: {fmtTs(md?.data.last_refresh_utc ?? null)}</small>
        </div>
      </header>
      <Banner md={md} error={error} />

      {md && hasData && (
        <section className="controls panel" aria-label="Filters">
          <label>Decision cutoff (London time, day before) <input type="time" value={cutoff} onChange={(e) => e.target.value && setCutoff(e.target.value)} /></label>
          <label>Delivery from <input type="date" min={md.decision_window.delivery_from} max={dateTo} value={dateFrom} onChange={(e) => e.target.value && setDateFrom(e.target.value)} /></label>
          <label>to <input type="date" min={dateFrom} max={md.decision_window.delivery_to} value={dateTo} onChange={(e) => e.target.value && setDateTo(e.target.value)} /></label>
          <p className="note"><strong>Assumption:</strong> {md.cutoff_rule.description} {md.cutoff_rule.status}</p>
        </section>
      )}

      {analysis && md && (analysis.metrics.matched_observations === 0
        ? <p className="empty panel">No matched forecast/actual periods in this range. See the banners above and the explorer below.</p>
        : <>
          <Kpis m={analysis.metrics} />
          <p className="note">Error = forecast − actual, in {md.unit}. {md.mape_note} Metrics use matched periods only; unmatched periods are excluded, never zero-filled.</p>
          <section className="panel"><h2>Forecast at decision time vs actual</h2>
            <p className="note">Each point uses the latest forecast published at or before the cutoff. Drag the slider under the chart to zoom.</p>
            <SeriesChart points={series} /></section>
          <section aria-labelledby="ins-h" className="panel"><h2 id="ins-h">Insights (computed from the data above)</h2>
            <ul className="insights">{analysis.insights.map((i) => <li key={i.id}>{i.text} <small>(n = {i.sample_size.toLocaleString()})</small></li>)}</ul>
            <p className="note">These describe forecast error only. This tool has no demand, price or thermal-generation data, so it does not compute shortfall or an optimal purchase quantity.</p></section>
          <h2>Forecast error analysis</h2>
          <ErrorCharts a={analysis} />
        </>)}
      {md && hasData && <PeriodExplorer cutoff={cutoff} dateFrom={dateFrom} dateTo={dateTo} />}
      {!hasData && md && !loading && md.data.state !== "error" && <p className="empty panel">No data loaded yet. Press “Refresh data”.</p>}
      <footer>{md?.sources.attribution}</footer>
    </div>
  );
}
