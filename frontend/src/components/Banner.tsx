import type { Metadata } from "../api";

/** Loading / error / partial-data states derived from backend metadata. */
export function Banner({ md, error }: { md: Metadata | null; error: string | null }) {
  if (error) return <div role="alert" className="banner err"><strong>Cannot load data.</strong> {error}</div>;
  if (!md) return <div role="status" className="banner info">Connecting to API…</div>;
  const d = md.data;
  return (
    <>
      {d.state === "loading" && <div role="status" className="banner info">Downloading Elexon data (first load can take a minute)…</div>}
      {d.state === "error" && <div role="alert" className="banner err"><strong>Elexon download failed.</strong> {d.last_error} No substitute data is shown.</div>}
      {d.state === "ready" && d.last_error && <div role="alert" className="banner warn">Last refresh failed ({d.last_error}). Showing previously downloaded data.</div>}
      {d.report?.warnings.map((w) => <div key={w} role="status" className="banner warn"><strong>Partial data:</strong> {w}</div>)}
    </>
  );
}
