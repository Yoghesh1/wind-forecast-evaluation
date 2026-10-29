import { useEffect, useState } from "react";
import { get, fmtMW, fmtTs } from "../api";
import type { PeriodsPage, Period, Vintages } from "../api";

const COLS: [string, string][] = [["start_utc", "Delivery (UTC)"], ["forecast_mw", "Forecast MW"], ["publish_utc", "Forecast published"],
  ["actual_mw", "Actual MW"], ["error_mw", "Error MW"], ["abs_error_mw", "|Error| MW"], ["status", "Status"]];

interface Props { cutoff: string; dateFrom: string; dateTo: string }

export function PeriodExplorer({ cutoff, dateFrom, dateTo }: Props) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sortBy, setSortBy] = useState("start_utc");
  const [dir, setDir] = useState<"asc" | "desc">("asc");
  const [data, setData] = useState<PeriodsPage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<Period | null>(null);
  const [vint, setVint] = useState<Vintages | null>(null);

  useEffect(() => { setPage(1); }, [search, status, cutoff, dateFrom, dateTo, sortBy, dir]);
  useEffect(() => {
    let live = true;
    get<PeriodsPage>("/api/v1/delivery-periods", { cutoff, date_from: dateFrom, date_to: dateTo, search, status, sort_by: sortBy, sort_dir: dir, page, page_size: 20 })
      .then((d) => { if (live) { setData(d); setErr(null); } })
      .catch((e: Error) => live && setErr(e.message));
    return () => { live = false; };
  }, [cutoff, dateFrom, dateTo, search, status, sortBy, dir, page]);
  useEffect(() => {
    if (!sel) { setVint(null); return; }
    get<Vintages>("/api/v1/delivery-periods/vintages", { start_utc: sel.start_utc, cutoff }).then(setVint).catch(() => setVint(null));
  }, [sel, cutoff]);

  const sort = (k: string) => { if (k === sortBy) setDir(dir === "asc" ? "desc" : "asc"); else { setSortBy(k); setDir("asc"); } };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <section className="panel" aria-labelledby="explorer-h">
      <h2 id="explorer-h">Delivery-period explorer</h2>
      <div className="toolbar">
        <label>Search <input type="search" placeholder="e.g. 2026-01-15 12:30" value={search} onChange={(e) => setSearch(e.target.value)} /></label>
        <label>Status <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option><option value="matched">Matched</option><option value="no_eligible_forecast">No eligible forecast</option>
          <option value="no_actual">No actual</option><option value="no_forecast_and_no_actual">Neither</option></select></label>
      </div>
      {err && <p role="alert" className="error">{err}</p>}
      <div className="scroll">
        <table>
          <thead><tr>
            <th>Decision cutoff (UTC)</th>
            {COLS.map(([k, label]) => (
              <th key={k} aria-sort={sortBy === k ? (dir === "asc" ? "ascending" : "descending") : "none"}>
                <button className="link" onClick={() => sort(k)}>{label}{sortBy === k ? (dir === "asc" ? " ▲" : " ▼") : ""}</button></th>))}
          </tr></thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.start_utc} className={sel?.start_utc === p.start_utc ? "sel" : ""}>
                <td>{fmtTs(p.cutoff_utc)}</td>
                <td><button className="link" onClick={() => setSel(p)} aria-label={`Inspect forecast vintage for ${p.start_utc}`}>{fmtTs(p.start_utc)}</button></td>
                <td>{fmtMW(p.forecast_mw)}</td><td>{fmtTs(p.publish_utc)}</td><td>{fmtMW(p.actual_mw)}</td>
                <td>{fmtMW(p.error_mw, true)}</td><td>{fmtMW(p.abs_error_mw)}</td>
                <td><span className={`badge ${p.status}`}>{p.status.replaceAll("_", " ")}</span>{p.only_after_cutoff && " (forecast only after cutoff)"}</td>
              </tr>))}
          </tbody>
        </table>
      </div>
      {data && data.total === 0 && <p className="empty">No delivery periods match these filters.</p>}
      <div className="pager">
        <button onClick={() => setPage(page - 1)} disabled={page <= 1}>Previous</button>
        <span>Page {page} of {pages} · {data?.total.toLocaleString() ?? "…"} periods</span>
        <button onClick={() => setPage(page + 1)} disabled={page >= pages}>Next</button>
      </div>
      {sel && vint && (
        <aside className="vintage" aria-label="Forecast vintages">
          <h3>Forecast vintages for {fmtTs(vint.start_utc)}</h3>
          <p>Decision cutoff: <strong>{fmtTs(vint.cutoff_utc)}</strong>. Rule: {vint.cutoff_rule}.</p>
          <table><thead><tr><th>Published</th><th>Forecast MW</th><th>Eligible?</th><th>Selected</th></tr></thead>
            <tbody>{vint.vintages.map((v) => (
              <tr key={v.publish_utc} className={v.selected ? "sel" : ""}>
                <td>{fmtTs(v.publish_utc)}</td><td>{fmtMW(v.forecast_mw)}</td>
                <td>{v.eligible ? `Yes (${Math.round(v.minutes_before_cutoff)} min before cutoff)` : `No (${Math.round(-v.minutes_before_cutoff)} min after cutoff)`}</td>
                <td>{v.selected ? "✔ latest eligible" : ""}</td></tr>))}</tbody></table>
          {vint.vintages.length === 0 && <p className="empty">No forecasts exist for this delivery period.</p>}
          <button onClick={() => setSel(null)}>Close</button>
        </aside>)}
    </section>
  );
}
