import { Bar, BarChart, CartesianGrid, Legend, Line, ComposedChart, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { Analysis } from "../api";
import { fmtMW, fmtTs } from "../api";

export function ErrorCharts({ a }: { a: Analysis }) {
  const max = Math.max(1000, ...a.scatter.map((p) => Math.max(p.actual_mw, p.forecast_mw)));
  const hist = a.histogram.map((b) => ({ ...b, label: `${b.from_mw}…${b.to_mw}` }));
  return (
    <div className="grid2">
      <figure className="panel">
        <figcaption><h3>Daily MAE &amp; RMSE (MW)</h3></figcaption>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={a.daily}><CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(8)} /><YAxis width={44} /><Tooltip /><Legend />
            <Bar dataKey="mae_mw" name="MAE" fill="var(--c-actual)" isAnimationActive={false} />
            <Line dataKey="rmse_mw" name="RMSE" stroke="var(--c-fc)" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
      <figure className="panel">
        <figcaption><h3>Daily bias (forecast − actual, MW)</h3></figcaption>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={a.daily}><CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(8)} /><YAxis width={50} /><Tooltip />
            <ReferenceLine y={0} stroke="var(--text)" />
            <Bar dataKey="bias_mw" name="Bias" fill="var(--c-fc)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </figure>
      <figure className="panel">
        <figcaption><h3>Error distribution (periods per error band, MW)</h3></figcaption>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={hist}><CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={30} tick={{ fontSize: 11 }} /><YAxis width={40} /><Tooltip />
            <Bar dataKey="count" name="Periods" fill="var(--c-actual)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </figure>
      <figure className="panel">
        <figcaption><h3>Forecast vs actual (dashed = perfect forecast)</h3></figcaption>
        <ResponsiveContainer width="100%" height={260}>
          <ScatterChart margin={{ left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis type="number" dataKey="actual_mw" name="Actual" domain={[0, max]} tickFormatter={(v: number) => `${v / 1000}k`} />
            <YAxis type="number" dataKey="forecast_mw" name="Forecast" domain={[0, max]} width={44} tickFormatter={(v: number) => `${v / 1000}k`} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: max, y: max }]} stroke="var(--text)" strokeDasharray="5 4" />
            <Scatter data={a.scatter} fill="var(--c-actual)" fillOpacity={0.35} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </figure>
      <figure className="panel wide">
        <figcaption><h3>MAE by local time of day (MW)</h3></figcaption>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.time_of_day}><CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="slot" interval={3} /><YAxis width={44} /><Tooltip />
            <Bar dataKey="mae_mw" name="MAE" fill="var(--c-actual)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </figure>
      <div className="panel wide">
        <h3>Ten largest absolute errors</h3>
        <div className="scroll">
          <table><thead><tr><th>Delivery (UTC)</th><th>Forecast</th><th>Actual</th><th>Error</th><th>Published</th></tr></thead>
            <tbody>{a.largest_errors.map((e) => (
              <tr key={e.start_utc}><td>{fmtTs(e.start_utc)}</td><td>{fmtMW(e.forecast_mw)}</td><td>{fmtMW(e.actual_mw)}</td>
                <td className={e.error_mw > 0 ? "pos" : "neg"}>{fmtMW(e.error_mw, true)}</td><td>{fmtTs(e.publish_utc)}</td></tr>))}
            </tbody></table>
        </div>
      </div>
    </div>
  );
}
