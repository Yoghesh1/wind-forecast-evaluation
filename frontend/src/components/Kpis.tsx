import type { Metrics } from "../api";
import { fmtMW } from "../api";

interface CardProps { label: string; value: string; unit?: string; def: string; ctx?: string }
function Card({ label, value, unit, def, ctx }: CardProps) {
  return (
    <article className="kpi" aria-label={label}>
      <h3>{label}</h3>
      <p className="kpi-value">{value}<span className="unit">{unit}</span></p>
      <p className="kpi-def">{def}</p>
      {ctx && <p className="kpi-ctx">{ctx}</p>}
    </article>
  );
}

export function Kpis({ m }: { m: Metrics }) {
  const bias = m.bias_mw;
  const biasCtx = bias == null ? undefined : bias > 0 ? "Over-forecasts on average" : bias < 0 ? "Under-forecasts on average" : "No average bias";
  return (
    <section className="kpis" aria-label="Key metrics">
      <Card label="MAE" value={fmtMW(m.mae_mw)} unit=" MW" def="Mean of |forecast − actual|."
        ctx={`n = ${m.matched_observations.toLocaleString()} matched periods`} />
      <Card label="RMSE" value={fmtMW(m.rmse_mw)} unit=" MW" def="Root of mean squared error; penalises large misses."
        ctx="Always ≥ MAE" />
      <Card label="Bias" value={fmtMW(bias, true)} unit=" MW" def="Mean of (forecast − actual). Positive = over-forecast." ctx={biasCtx} />
      <Card label="Matched / coverage" value={`${m.matched_observations.toLocaleString()}`}
        unit={m.coverage_pct == null ? "" : ` (${m.coverage_pct.toFixed(1)}%)`}
        def="Periods with both an eligible forecast and an actual, over all delivery periods."
        ctx={`${m.missing_forecast} no forecast · ${m.missing_actual} no actual`} />
      <Card label="MAPE (limited)" value={m.mape_pct == null ? "—" : m.mape_pct.toFixed(1)} unit={m.mape_pct == null ? "" : " %"}
        def={`Excludes actuals < ${m.mape_min_actual_mw} MW (unstable near zero).`}
        ctx={`n = ${m.mape_observations.toLocaleString()}, ${m.mape_excluded.toLocaleString()} excluded`} />
    </section>
  );
}
