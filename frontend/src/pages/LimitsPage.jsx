import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Ruler, ShieldCheck } from "lucide-react";

import { listLimits } from "@/lib/api";
import { LIMITS } from "@/constants/testIds";

export default function LimitsPage() {
  const [limits, setLimits] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLimits(await listLimits());
      } catch {
        toast.error("Failed to load NCEC limits");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const grouped = limits.reduce((acc, l) => {
    (acc[l.pollutant] = acc[l.pollutant] || []).push(l);
    return acc;
  }, {});

  return (
    <div data-testid={LIMITS.root} className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Ruler className="w-5 h-5 text-primary" /> KSA NCEC 2020 Ambient Air Quality Standards
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          Read-only regulatory reference. Basis:{" "}
          <span className="font-mono text-foreground">Royal Decree No. M/165, 19/11/1441 AH</span>.
          These limits drive the compliance verdicts on every generated report (Phase 3+).
        </p>
      </header>

      {loading ? (
        <div className="text-sm text-muted-foreground">Loading limits…</div>
      ) : (
        <section
          data-testid={LIMITS.table}
          className="border border-border rounded-sm overflow-hidden"
        >
          <div className="grid grid-cols-12 gap-3 bg-zinc-900/60 text-[10px] uppercase tracking-wider text-muted-foreground px-4 py-2 border-b border-border">
            <div className="col-span-2">Pollutant</div>
            <div className="col-span-3">Averaging period</div>
            <div className="col-span-2 text-right font-mono">Limit (µg/m³)</div>
            <div className="col-span-4">Allowable exceedances</div>
            <div className="col-span-1 text-right">Source</div>
          </div>
          {Object.entries(grouped).map(([pol, rows]) => (
            <div key={pol}>
              {rows.map((l, idx) => (
                <div
                  key={l.id}
                  data-testid={LIMITS.row(pol, l.averaging_period)}
                  className="grid grid-cols-12 gap-3 px-4 py-2.5 border-b border-border last:border-b-0 items-center hover:bg-zinc-900/30"
                >
                  <div className="col-span-2 font-mono font-medium">
                    {idx === 0 ? pol : <span className="text-muted-foreground">↳</span>}
                  </div>
                  <div className="col-span-3 text-sm">{l.averaging_period}</div>
                  <div className="col-span-2 text-right font-mono tabular">
                    {l.limit_ugm3.toLocaleString()}
                  </div>
                  <div className="col-span-4 text-sm text-muted-foreground">
                    {l.allowable_exceedances || "—"}
                  </div>
                  <div className="col-span-1 text-right text-[10px] text-muted-foreground flex items-center justify-end gap-1">
                    <ShieldCheck className="w-3 h-3" />
                    NCEC
                  </div>
                </div>
              ))}
            </div>
          ))}
        </section>
      )}

      <p className="text-[11px] text-muted-foreground">
        Note: CO and O₃ averages are rolling averages (8-hour). Others are fixed windows.
      </p>
    </div>
  );
}
