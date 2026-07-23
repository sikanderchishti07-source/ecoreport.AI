import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, CheckCircle2, FileText, Loader2, RefreshCw, Upload,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getSummary, listReadings } from "@/lib/api";

const POLLUTANTS = [
  { key: "SO2", label: "SO₂" },
  { key: "NO2", label: "NO₂" },
  { key: "CO", label: "CO" },
  { key: "O3", label: "O₃" },
  { key: "H2S", label: "H₂S" },
  { key: "PM10", label: "PM10" },
  { key: "PM25", label: "PM2.5" },
];

const num = (v, d = 1) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(d);

function Metric({ label, value, tone = "default", hint }) {
  const tones = {
    default: "text-foreground",
    good: "text-emerald-500",
    warn: "text-amber-500",
    bad: "text-red-500",
  };
  return (
    <div className="bg-secondary/50 rounded-sm p-3.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-2xl font-semibold mt-0.5 tabular ${tones[tone]}`}>
        {value}
      </div>
      {hint && <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

/** Verdict for one pollutant, derived from its period evaluations. */
function verdictOf(p) {
  if (!p) return { tone: "muted", text: "no data" };
  const evs = (p.period_evaluations || []).filter(
    (e) => e.averaging_period !== "1 Year"
  );
  if (evs.some((e) => e.verdict === "non-compliant"))
    return { tone: "bad", text: "exceedance" };
  if (p.hourly_capture_pct !== null && p.hourly_capture_pct < 75)
    return { tone: "warn", text: "low capture" };
  if (p.below_mdl_count && p.hourly_valid_count &&
      p.below_mdl_count >= p.hourly_valid_count)
    return { tone: "muted", text: "below detection" };
  const withLimit = evs.filter((e) => e.limit_ugm3);
  if (withLimit.length && p.hourly_max !== null) {
    const nearest = Math.min(
      ...withLimit.map((e) => p.hourly_max / e.limit_ugm3)
    );
    if (nearest >= 0.8) return { tone: "warn", text: "approaching limit" };
  }
  return { tone: "good", text: "compliant" };
}

const BAR = {
  good: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-red-500",
  muted: "bg-muted-foreground/40",
};

export default function CampaignDashboard({ campaign, onGoTo }) {
  const [summary, setSummary] = useState(null);
  const [coverage, setCoverage] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await getSummary(campaign.id);
      setSummary(s);
      const rs = await listReadings(campaign.id, { limit: 1000 });
      setCoverage(
        (rs || []).map((r) => ({
          t: r.timestamp,
          state: !r.valid ? "invalid"
            : (r.auto_flagged_fields || []).length ? "partial" : "valid",
        }))
      );
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not load the summary");
    } finally {
      setLoading(false);
    }
  }, [campaign.id]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading campaign summary…
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="border border-dashed border-border rounded-sm p-8 text-center">
        <Upload className="w-5 h-5 mx-auto text-muted-foreground" />
        <p className="text-sm mt-2">{error || "No summary yet"}</p>
        <p className="text-xs text-muted-foreground mt-1">
          Upload monitoring readings to see compliance at a glance.
        </p>
      </div>
    );
  }

  const P = Object.fromEntries((summary.pollutants || []).map((p) => [p.pollutant, p]));
  const exceedances = (summary.pollutants || []).reduce(
    (n, p) => n + (p.period_evaluations || []).filter(
      (e) => e.verdict === "non-compliant").length, 0);
  const capture = summary.overall_hourly_capture_pct;
  const ready = capture !== null && capture >= 75;

  const totals = coverage.reduce((acc, c) => {
    acc[c.state] = (acc[c.state] || 0) + 1;
    return acc;
  }, {});
  const expected = summary.monitoring_hours || coverage.length || 1;
  const missing = Math.max(expected - coverage.length, 0);

  return (
    <div className="space-y-5">
      {/* status */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{campaign.project_name}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {campaign.site_name} · {summary.monitoring_hours} monitoring hours
          </p>
        </div>
        <div className="flex items-center gap-2">
          {ready ? (
            <Badge className="rounded-sm bg-emerald-500/15 text-emerald-500 border-0">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Ready to report
            </Badge>
          ) : (
            <Badge className="rounded-sm bg-amber-500/15 text-amber-500 border-0">
              <AlertTriangle className="w-3.5 h-3.5 mr-1" /> Needs attention
            </Badge>
          )}
          <Button variant="outline" size="icon" className="rounded-sm h-8 w-8"
                  onClick={load} title="Refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Metric label="Data capture" value={`${num(capture)}%`}
                tone={capture >= 75 ? "good" : "warn"}
                hint={capture < 75 ? "below the 75% requirement" : undefined} />
        <Metric label="Valid hours"
                value={`${totals.valid || 0} / ${expected}`} />
        <Metric label="Exceedances" value={exceedances}
                tone={exceedances ? "bad" : "good"} />
        <Metric label="Invalidated"
                value={(totals.invalid || 0) + (totals.partial || 0)}
                tone={(totals.invalid || 0) ? "warn" : "default"} />
      </div>

      {/* compliance by pollutant */}
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold mb-3">Compliance by pollutant</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          {POLLUTANTS.map(({ key, label }) => {
            const p = P[key];
            const v = verdictOf(p);
            const lim = (p?.period_evaluations || [])
              .find((e) => e.limit_ugm3)?.limit_ugm3;
            return (
              <div key={key} className="flex gap-2.5 py-1.5">
                <span className={`w-[3px] rounded-sm shrink-0 ${BAR[v.tone]}`} />
                <div className="min-w-0">
                  <div className="text-sm">{label}</div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    max {num(p?.hourly_max)}{lim ? ` · limit ${num(lim, 0)}` : ""}
                  </div>
                  <div className={`text-[11px] ${
                    v.tone === "bad" ? "text-red-500"
                    : v.tone === "warn" ? "text-amber-500"
                    : v.tone === "good" ? "text-emerald-500"
                    : "text-muted-foreground"}`}>
                    {v.text}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* coverage timeline */}
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold mb-3">Data coverage</h3>
        <div className="flex gap-px h-6 rounded-sm overflow-hidden">
          {coverage.map((c, i) => (
            <span
              key={i}
              title={new Date(c.t).toLocaleString()}
              className={`flex-1 ${
                c.state === "valid" ? "bg-emerald-500"
                : c.state === "partial" ? "bg-amber-500" : "bg-red-500"}`}
            />
          ))}
          {missing > 0 && (
            <span className="bg-muted-foreground/30"
                  style={{ flex: missing }} title={`${missing} hour(s) missing`} />
          )}
        </div>
        <div className="flex flex-wrap gap-4 mt-2.5 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> valid
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-amber-500" /> partly flagged
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-red-500" /> invalidated
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-muted-foreground/30" /> missing
          </span>
        </div>
      </div>

      {/* meteorology */}
      {summary.meteorology && (
        <div className="border border-border rounded-sm p-4">
          <h3 className="text-sm font-semibold mb-3">Meteorology</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-xs text-muted-foreground">Temperature</div>
              <div className="tabular">{num(summary.meteorology.temp_min)} – {num(summary.meteorology.temp_max)} °C</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Humidity</div>
              <div className="tabular">{num(summary.meteorology.rh_min)} – {num(summary.meteorology.rh_max)} %</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Wind speed</div>
              <div className="tabular">{num(summary.meteorology.wind_speed_min)} – {num(summary.meteorology.wind_speed_max)} m/s</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Prevailing</div>
              <div>{summary.wind_rose?.prevailing_direction || "—"}</div>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button className="rounded-sm h-9" onClick={() => onGoTo?.("reports")}>
          <FileText className="w-4 h-4 mr-1.5" /> Generate report
        </Button>
        <Button variant="outline" className="rounded-sm h-9"
                onClick={() => onGoTo?.("readings")}>
          Review readings
        </Button>
      </div>
    </div>
  );
}
