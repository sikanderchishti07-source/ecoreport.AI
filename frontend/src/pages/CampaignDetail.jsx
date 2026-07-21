import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  CheckCircle2,
  Upload,
  Pencil,
  Wind,
  RefreshCcw,
  Plus,
  X,
  Trash2,
  FileWarning,
} from "lucide-react";

import {
  clearReadings,
  flagReading,
  getCampaign,
  listReadings,
  listUploads,
  updateCampaign,
} from "@/lib/api";
import { CAMPAIGN_DETAIL } from "@/constants/testIds";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const DEFAULT_BINS = [
  { label: "Calm", min: 0, max: 2.1 },
  { label: "2.10-3.60", min: 2.1, max: 3.6 },
  { label: "≥3.60", min: 3.6, max: null },
];

const POLLUTANT_COLS = ["SO2", "NO", "NO2", "NOx", "CO", "H2S", "O3", "PM10", "PM25"];
const MET_COLS = ["Temp", "RH", "Pressure", "WindSpeed", "WindDirection"];
const NUMERIC_COLS = [...POLLUTANT_COLS, ...MET_COLS];

function fmt(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1000) return n.toFixed(0);
  return n.toFixed(2);
}

export default function CampaignDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [campaign, setCampaign] = useState(null);
  const [readings, setReadings] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [bins, setBins] = useState(DEFAULT_BINS);
  const [savingBins, setSavingBins] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [c, r, u] = await Promise.all([
        getCampaign(id),
        listReadings(id, { limit: 2000, offset: 0 }),
        listUploads(id),
      ]);
      setCampaign(c);
      setReadings(r);
      setUploads(u);
      setBins((c.wind_rose_bins && c.wind_rose_bins.length) ? c.wind_rose_bins : DEFAULT_BINS);
    } catch {
      toast.error("Failed to load campaign");
    } finally {
      setLoading(false);
    }
  };

  // load depends on `id`; intentional single-arg dep to reload on nav.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [id]);

  const toggleFlag = async (r) => {
    const nextValid = !r.valid;
    // Optimistic update
    setReadings((rs) =>
      rs.map((x) =>
        x.id === r.id
          ? {
              ...x,
              valid: nextValid,
              invalidation_reason: nextValid ? null : x.invalidation_reason || "manually flagged",
            }
          : x
      )
    );
    try {
      await flagReading(r.id, {
        valid: nextValid,
        invalidation_reason: nextValid ? null : "manually flagged",
      });
    } catch {
      toast.error("Failed to update flag");
      load();
    }
  };

  const handleClearReadings = async () => {
    try {
      await clearReadings(id);
      toast.success("All readings cleared");
      load();
    } catch {
      toast.error("Clear failed");
    }
  };

  const saveBins = async () => {
    setSavingBins(true);
    try {
      // Normalize numeric fields
      const clean = bins.map((b) => ({
        label: b.label,
        min: Number(b.min),
        max: b.max === "" || b.max === null || b.max === undefined ? null : Number(b.max),
      }));
      await updateCampaign(id, { wind_rose_bins: clean });
      toast.success("Wind-rose bins saved");
    } catch {
      toast.error("Save failed");
    } finally {
      setSavingBins(false);
    }
  };

  const resetBins = () => setBins(DEFAULT_BINS);

  const validCount = useMemo(() => readings.filter((r) => r.valid).length, [readings]);

  if (loading || !campaign) {
    return <div className="text-sm text-muted-foreground">Loading…</div>;
  }

  return (
    <div data-testid={CAMPAIGN_DETAIL.root} className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => nav("/campaigns")}
            className="rounded-sm"
          >
            <ArrowLeft className="w-4 h-4 mr-1" /> Campaigns
          </Button>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{campaign.project_name}</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              {campaign.site_name} · {campaign.client}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="rounded-sm"
            data-testid={CAMPAIGN_DETAIL.editBtn}
            onClick={() => nav(`/campaigns/${id}/edit`)}
          >
            <Pencil className="w-4 h-4 mr-2" /> Edit
          </Button>
          <Button
            className="rounded-sm"
            data-testid={CAMPAIGN_DETAIL.uploadBtn}
            onClick={() => nav(`/campaigns/${id}/upload`)}
          >
            <Upload className="w-4 h-4 mr-2" /> Upload data
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="rounded-sm bg-zinc-900/60 border border-border p-1 h-auto">
          <TabsTrigger value="overview" data-testid={CAMPAIGN_DETAIL.tabOverview} className="rounded-sm">
            Overview
          </TabsTrigger>
          <TabsTrigger value="readings" data-testid={CAMPAIGN_DETAIL.tabReadings} className="rounded-sm">
            Readings <span className="ml-1.5 font-mono tabular text-muted-foreground">{readings.length}</span>
          </TabsTrigger>
          <TabsTrigger value="settings" data-testid={CAMPAIGN_DETAIL.tabSettings} className="rounded-sm">
            Settings
          </TabsTrigger>
          <TabsTrigger value="reports" data-testid={CAMPAIGN_DETAIL.tabReports} className="rounded-sm">
            Reports
          </TabsTrigger>
        </TabsList>

        {/* OVERVIEW */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Readings ingested" value={readings.length} mono />
            <StatCard label="Valid readings" value={validCount} mono accent="text-emerald-400" />
            <StatCard label="Invalid readings" value={readings.length - validCount} mono accent="text-red-400" />
            <StatCard label="Uploads" value={uploads.length} mono />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <InfoCard title="Project">
              <KV k="Client" v={campaign.client} />
              <KV k="Provider" v={campaign.provider} />
              <KV k="Report number" v={campaign.report_number || "—"} mono />
              <KV k="Revision" v={campaign.revision || "—"} mono />
              <KV k="Prepared by" v={campaign.prepared_by || "—"} />
              <KV k="Project supervision" v={campaign.project_supervision || "—"} />
              <KV k="Reporting date" v={campaign.reporting_date ? new Date(campaign.reporting_date).toLocaleDateString() : "—"} />
            </InfoCard>
            <InfoCard title="Site & window">
              <KV k="Site name" v={campaign.site_name} />
              <KV k="Coordinates" v={`${campaign.latitude.toFixed(6)}, ${campaign.longitude.toFixed(6)}`} mono />
              <KV k="Inlet height" v={`${campaign.inlet_height_m} m`} mono />
              <KV k="Monitoring start" v={new Date(campaign.monitoring_start).toLocaleString()} mono />
              <KV k="Monitoring end" v={new Date(campaign.monitoring_end).toLocaleString()} mono />
              <KV k="Status" v={campaign.status} />
            </InfoCard>
          </div>

          {uploads.length > 0 && (
            <InfoCard title="Recent uploads">
              <div className="text-xs">
                <div className="grid grid-cols-12 text-[11px] uppercase tracking-wider text-muted-foreground pb-1.5 border-b border-border">
                  <div className="col-span-4">File</div>
                  <div className="col-span-2">Type</div>
                  <div className="col-span-2 text-right font-mono">Ingested</div>
                  <div className="col-span-2 text-right font-mono">Skipped</div>
                  <div className="col-span-2 text-right">When</div>
                </div>
                {uploads.map((u) => (
                  <div key={u.id} className="grid grid-cols-12 py-1.5 border-b border-border last:border-b-0">
                    <div className="col-span-4 truncate">{u.filename}</div>
                    <div className="col-span-2 font-mono uppercase text-muted-foreground">{u.file_type}</div>
                    <div className="col-span-2 text-right font-mono tabular text-emerald-400">{u.rows_ingested}</div>
                    <div className="col-span-2 text-right font-mono tabular text-amber-400">{u.rows_skipped}</div>
                    <div className="col-span-2 text-right text-muted-foreground">
                      {new Date(u.uploaded_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </InfoCard>
          )}
        </TabsContent>

        {/* READINGS */}
        <TabsContent value="readings" className="mt-4 space-y-3">
          {readings.length === 0 ? (
            <div className="border border-dashed border-border rounded-sm p-10 text-center">
              <FileWarning className="w-6 h-6 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">
                No readings yet. Upload a CSV or XLSX to populate this campaign.
              </p>
              <Button
                className="mt-4 rounded-sm"
                onClick={() => nav(`/campaigns/${id}/upload`)}
              >
                <Upload className="w-4 h-4 mr-2" /> Upload data
              </Button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  Showing {readings.length} readings · toggle validity per row (manual QA).
                </span>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      data-testid={CAMPAIGN_DETAIL.clearAllReadings}
                      className="rounded-sm text-red-400"
                    >
                      <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Clear all readings
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="rounded-sm">
                    <AlertDialogHeader>
                      <AlertDialogTitle>Clear all readings?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This wipes every reading for this campaign so you can re-upload a corrected file.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel className="rounded-sm">Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        className="rounded-sm bg-red-600 hover:bg-red-500"
                        onClick={handleClearReadings}
                      >
                        Clear
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
              <div
                data-testid={CAMPAIGN_DETAIL.readingsTable}
                className="border border-border rounded-sm overflow-x-auto"
              >
                <table className="w-full text-xs font-mono tabular">
                  <thead className="bg-zinc-900/60 text-muted-foreground text-[10px] uppercase tracking-wider">
                    <tr>
                      <th className="text-left px-2 py-2 sticky left-0 bg-zinc-900/90 z-10">Timestamp</th>
                      {NUMERIC_COLS.map((c) => (
                        <th key={c} className="text-right px-2 py-2">{c}</th>
                      ))}
                      <th className="text-center px-2 py-2">Valid</th>
                    </tr>
                  </thead>
                  <tbody>
                    {readings.map((r) => (
                      <tr
                        key={r.id}
                        data-testid={CAMPAIGN_DETAIL.readingRow(r.id)}
                        className={`border-t border-border ${r.valid ? "row-valid" : "row-invalid"}`}
                      >
                        <td className="text-left px-2 py-1.5 whitespace-nowrap sticky left-0 bg-background/95">
                          {new Date(r.timestamp).toLocaleString(undefined, {
                            year: "numeric", month: "2-digit", day: "2-digit",
                            hour: "2-digit", minute: "2-digit",
                          })}
                        </td>
                        {NUMERIC_COLS.map((c) => (
                          <td key={c} className="text-right px-2 py-1.5">{fmt(r[c])}</td>
                        ))}
                        <td className="text-center px-2 py-1.5">
                          <Switch
                            data-testid={CAMPAIGN_DETAIL.readingFlagToggle(r.id)}
                            checked={r.valid}
                            onCheckedChange={() => toggleFlag(r)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </TabsContent>

        {/* SETTINGS */}
        <TabsContent value="settings" className="mt-4">
          <div className="border border-border rounded-sm">
            <header className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wind className="w-4 h-4 text-primary" />
                <h2 className="text-sm font-semibold">Wind-rose speed classes</h2>
              </div>
              <span className="text-[11px] text-muted-foreground">
                Configurable per campaign · defaults: Calm / 2.10–3.60 / ≥3.60
              </span>
            </header>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-12 text-[10px] uppercase tracking-wider text-muted-foreground">
                <div className="col-span-4">Label</div>
                <div className="col-span-3">Min (m/s)</div>
                <div className="col-span-3">Max (m/s) — blank = open-ended</div>
                <div className="col-span-2 text-right">Action</div>
              </div>
              {bins.map((b, idx) => (
                <div
                  key={idx}
                  data-testid={CAMPAIGN_DETAIL.binRow(idx)}
                  className="grid grid-cols-12 gap-2 items-center"
                >
                  <div className="col-span-4">
                    <Input
                      data-testid={CAMPAIGN_DETAIL.binLabel(idx)}
                      value={b.label}
                      onChange={(e) => setBins((bs) => bs.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)))}
                      className="rounded-sm"
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      data-testid={CAMPAIGN_DETAIL.binMin(idx)}
                      value={b.min}
                      onChange={(e) => setBins((bs) => bs.map((x, i) => (i === idx ? { ...x, min: e.target.value } : x)))}
                      type="number"
                      step="0.01"
                      className="rounded-sm font-mono"
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      data-testid={CAMPAIGN_DETAIL.binMax(idx)}
                      value={b.max ?? ""}
                      onChange={(e) => setBins((bs) => bs.map((x, i) => (i === idx ? { ...x, max: e.target.value } : x)))}
                      type="number"
                      step="0.01"
                      className="rounded-sm font-mono"
                      placeholder="—"
                    />
                  </div>
                  <div className="col-span-2 text-right">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      data-testid={CAMPAIGN_DETAIL.binRemove(idx)}
                      onClick={() => setBins((bs) => bs.filter((_, i) => i !== idx))}
                      className="rounded-sm text-red-400"
                      disabled={bins.length <= 1}
                    >
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
              <div className="flex items-center justify-between pt-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  data-testid={CAMPAIGN_DETAIL.binAddBtn}
                  onClick={() => setBins((bs) => [...bs, { label: "New bin", min: 0, max: null }])}
                  className="rounded-sm"
                >
                  <Plus className="w-3.5 h-3.5 mr-1.5" /> Add bin
                </Button>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    data-testid={CAMPAIGN_DETAIL.binResetBtn}
                    onClick={resetBins}
                    className="rounded-sm"
                  >
                    <RefreshCcw className="w-3.5 h-3.5 mr-1.5" /> Reset to default
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    onClick={saveBins}
                    disabled={savingBins}
                    data-testid={CAMPAIGN_DETAIL.binSaveBtn}
                    className="rounded-sm"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                    {savingBins ? "Saving…" : "Save bins"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* REPORTS (placeholder) */}
        <TabsContent value="reports" className="mt-4">
          <div className="border border-dashed border-border rounded-sm p-10 text-center">
            <h3 className="text-sm font-semibold">Reports</h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
              Report generation lands in later phases: calculation engine → English report → graphs →
              Arabic/bilingual → versioning → storage & auth.
              For now, once readings are ingested and QA-flagged you can proceed to Phase 2.
            </p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatCard({ label, value, mono, accent }) {
  return (
    <div className="border border-border rounded-sm p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`text-2xl mt-1 ${mono ? "font-mono tabular" : ""} ${accent || ""}`}>{value}</div>
    </div>
  );
}

function InfoCard({ title, children }) {
  return (
    <section className="border border-border rounded-sm">
      <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-zinc-900/40">
        {title}
      </header>
      <div className="p-4 space-y-2">{children}</div>
    </section>
  );
}

function KV({ k, v, mono }) {
  return (
    <div className="grid grid-cols-3 gap-2 text-sm">
      <div className="text-muted-foreground text-xs col-span-1">{k}</div>
      <div className={`col-span-2 ${mono ? "font-mono tabular" : ""}`}>{v}</div>
    </div>
  );
}
