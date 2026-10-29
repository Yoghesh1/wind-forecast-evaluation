import { CartesianGrid, Brush, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesPoint } from "../api";
import { fmtMW, fmtTs } from "../api";

function Tip({ active, payload }: { active?: boolean; payload?: { payload: SeriesPoint }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tip" role="status">
      <strong>{fmtTs(p.start_utc)}</strong>
      <div>Actual: {fmtMW(p.actual_mw)} MW</div>
      <div>Forecast: {fmtMW(p.forecast_mw)} MW</div>
      <div>Error (F − A): {fmtMW(p.error_mw, true)} MW</div>
      <div>Forecast published: {fmtTs(p.publish_utc)}</div>
      {p.status !== "matched" && <div className="warn">Status: {p.status.replaceAll("_", " ")}</div>}
    </div>
  );
}

export function SeriesChart({ points }: { points: SeriesPoint[] }) {
  return (
    <div className="chart" role="img" aria-label="Line chart of actual wind generation versus decision-time forecast, half-hourly">
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
          <XAxis dataKey="start_utc" tickFormatter={(v: string) => v.slice(5, 10)} minTickGap={40} />
          <YAxis tickFormatter={(v: number) => `${v / 1000}k`} width={44} label={{ value: "MW", angle: -90, position: "insideLeft" }} />
          <Tooltip content={<Tip />} />
          <Legend />
          {/* connectNulls=false: gaps stay gaps, nothing is interpolated */}
          <Line name="Actual (FUELHH)" dataKey="actual_mw" stroke="var(--c-actual)" dot={false} strokeWidth={1.6} isAnimationActive={false} connectNulls={false} />
          <Line name="Forecast at decision time (WINDFOR)" dataKey="forecast_mw" stroke="var(--c-fc)" dot={false} strokeWidth={1.6} isAnimationActive={false} connectNulls={false} />
          <Brush dataKey="start_utc" height={24} stroke="var(--c-actual)" tickFormatter={(v: string) => v.slice(5, 10)} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
