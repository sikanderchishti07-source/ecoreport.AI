import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowLeft, CalendarCheck, CheckCircle2, FileSpreadsheet,
  Loader2, ShieldAlert, UploadCloud,
} from "lucide-react";

import {
  adoptDataWindow, getCampaign, uploadNoiseReadings, uploadReadings,
} from "@/lib/api";
import { UPLOAD } from "@/constants/testIds";
import { Button } from "@/components/ui/button";

const REQUIRED = ["timestamp"];

/** A stored timestamp as a person reads it. */
function fmtWindow(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
const EXPECTED_COLS = [
  "timestamp",
  "SO2", "NO", "NO2", "NOx", "CO", "H2S", "O3", "PM10", "PM25",
  "Temp", "RH", "Pressure", "WindSpeed", "WindDirection",
];

export default function UploadPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [campaign, setCampaign] = useState(null);
  const [adopting, setAdopting] = useState(false);

  useEffect(() => {
    getCampaign(id).then(setCampaign).catch(() => toast.error("Failed to load campaign"));
  }, [id]);

  const onFile = (f) => {
    if (!f) return;
    const name = f.name.toLowerCase();
    if (!name.endsWith(".csv") && !name.endsWith(".xlsx") && !name.endsWith(".xls")) {
      toast.error("Only .csv or .xlsx accepted");
      return;
    }
    setFile(f);
    setResult(null);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) onFile(e.dataTransfer.files[0]);
  };

  const isNoise = campaign?.campaign_type === "noise";

  const submit = async () => {
    if (!file) {
      toast.error("Choose a file first");
      return;
    }
    setUploading(true);
    try {
      if (isNoise) {
        // The noise ingest replies with a different shape — rows, flags,
        // first and last timestamps — so it is handled here rather than
        // funnelled through the analyser result panel.
        const res = await uploadNoiseReadings(id, file);
        setResult(null);
        if (res.rows > 0) {
          toast.success(
            `${res.rows.toLocaleString()} intervals ingested` +
            (res.auto_flagged
              ? ` — ${res.auto_flagged} flagged outside the plausible range`
              : ""));
          // The window decides which intervals a report is built from and
          // what its capture figure is, so it is stated rather than left to
          // be discovered on the campaign screen.
          if (res.window_action === "set") {
            toast.info(
              `Monitoring window set from the file: `
              + `${fmtWindow(res.data_start)} to ${fmtWindow(res.data_end)}`);
          } else if (res.window_action === "differs") {
            toast.warning(
              `The window on this campaign does not match the file, which `
              + `covers ${fmtWindow(res.data_start)} to `
              + `${fmtWindow(res.data_end)}. Nothing was changed.`,
              { duration: 12000 });
          }
          nav(`/campaigns/${id}`);
        } else {
          toast.warning("No rows ingested — check the file's columns");
        }
        return;
      }
      const res = await uploadReadings(id, file);
      setResult(res);
      const warnings = res.upload_log.units_warnings || [];
      if (warnings.length > 0) {
        // A units mistake produces plausible-looking numbers, so it has to
        // interrupt rather than sit in a log nobody opens.
        toast.error("Check the gas units before generating a report");
      } else if (res.upload_log.rows_ingested > 0) {
        toast.success(`${res.upload_log.rows_ingested} rows ingested`);
      } else {
        toast.warning("No rows ingested — see errors");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const adoptWindow = async () => {
    setAdopting(true);
    try {
      const out = await adoptDataWindow(id);
      toast.success(
        `Monitoring window set to ${fmtWindow(out.monitoring_start)} `
        + `to ${fmtWindow(out.monitoring_end)}`);
      // The panel described a disagreement that no longer exists, so it is
      // cleared rather than left offering a choice already made.
      setResult((prev) => (prev
        ? { ...prev,
            upload_log: { ...prev.upload_log, window_action: "matches" } }
        : prev));
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not set the window");
    } finally {
      setAdopting(false);
    }
  };

  const unitsWarnings = result?.upload_log?.units_warnings || [];
  const unitsApplied = result?.upload_log?.units_applied || {};

  return (
    <div data-testid={UPLOAD.root} className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => nav(`/campaigns/${id}`)}
          className="rounded-sm"
        >
          <ArrowLeft className="w-4 h-4 mr-1" /> Campaign
        </Button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Upload monitoring data</h1>
          {campaign && (
            <p className="text-xs text-muted-foreground mt-0.5">{campaign.project_name}</p>
          )}
        </div>
      </div>

      {isNoise ? (
      <section className="border border-border rounded-sm">
        <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-secondary/40">
          Expected columns — sound level meter export
        </header>
        <div className="p-4 space-y-2">
          <div className="grid grid-cols-4 gap-2 text-xs font-mono max-w-md">
            {["No.", "Date", "Time", "dB"].map((c) => (
              <span key={c}
                    className="border border-border rounded-sm px-2 py-1 text-primary border-primary/40 text-center">
                {c}
              </span>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">
            One row per logged interval, exactly as the meter exports it.
            Times that run past midnight under one date are handled.
            Re-uploading replaces the previous data for this campaign.
          </p>
        </div>
      </section>
      ) : (
      <section className="border border-border rounded-sm">
        <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-secondary/40">
          Expected columns (order-agnostic)
        </header>
        <div className="p-4 grid grid-cols-3 md:grid-cols-5 gap-2 text-xs font-mono">
          {EXPECTED_COLS.map((c) => (
            <span
              key={c}
              className={`border border-border rounded-sm px-2 py-1 ${REQUIRED.includes(c) ? "text-primary border-primary/40" : "text-muted-foreground"}`}
            >
              {c}
              {REQUIRED.includes(c) && <span className="text-red-400 ml-1">*</span>}
            </span>
          ))}
        </div>
        <div className="px-4 pb-4 text-[11px] text-muted-foreground space-y-0.5">
          <div>• Gas units come from the campaign's per-gas settings, or from a units row inside the file. PM10 / PM2.5: µg/m³</div>
          <div>• Temp: °C · RH: % · Pressure: hPa · Wind speed: m/s · Wind direction: ° (0–360)</div>
          <div>• Cadence: 1 row per hour · Timestamps: ISO-8601 (YYYY-MM-DD HH:MM:SS)</div>
          <div>• QA flag is not read from the file — mark rows as invalid via the Readings tab after upload.</div>
        </div>
      </section>
      )}

      <label
        htmlFor="upload-input"
        data-testid={UPLOAD.dropzone}
        data-active={dragActive}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        className="dropzone block rounded-sm p-10 text-center cursor-pointer bg-secondary/20"
      >
        <UploadCloud className="w-8 h-8 mx-auto text-muted-foreground" />
        <p className="mt-3 text-sm">
          <span className="text-primary underline decoration-dotted">Click to browse</span>{" "}
          or drop a .csv / .xlsx / .xls file here
        </p>
        {file && (
          <div className="mt-4 inline-flex items-center gap-2 text-xs font-mono border border-border rounded-sm px-2 py-1 bg-background/60">
            <FileSpreadsheet className="w-3.5 h-3.5" />
            {file.name} · {(file.size / 1024).toFixed(1)} kB
          </div>
        )}
        <input
          id="upload-input"
          ref={inputRef}
          data-testid={UPLOAD.fileInput}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])}
        />
      </label>

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          className="rounded-sm"
          onClick={() => { setFile(null); setResult(null); if (inputRef.current) inputRef.current.value = ""; }}
          disabled={!file}
        >
          Reset
        </Button>
        <Button
          data-testid={UPLOAD.submitBtn}
          className="rounded-sm"
          onClick={submit}
          disabled={!file || uploading}
        >
          {uploading ? "Uploading…" : "Ingest file"}
        </Button>
      </div>

      {/* Units problems are shown above the result panel, not inside it.
          A wrong unit yields numbers that look entirely normal, so this is
          the one message that must not be scrolled past. */}
      {unitsWarnings.length > 0 && (
        <section
          data-testid="upload-units-warning"
          className="border-2 border-red-600 bg-red-950/30 rounded-sm"
        >
          <header className="px-4 py-2 border-b border-red-800 text-[11px] uppercase tracking-wider text-red-300 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4" />
            Check the gas units before generating a report
          </header>
          <div className="p-4 space-y-3">
            <ul className="space-y-2">
              {unitsWarnings.map((w, i) => (
                <li key={i} className="text-sm text-red-200 leading-relaxed">
                  {w}
                </li>
              ))}
            </ul>
            <p className="text-[11px] text-red-300/80">
              The data has been ingested. Nothing is blocked — but a wrong unit
              produces figures that look plausible and are wrong by a factor of
              between 1.4 and 1000. Correct the units, upload the file again,
              and the readings will be replaced.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="rounded-sm border-red-700 text-red-200 hover:bg-red-900/40"
              onClick={() => nav(`/campaigns/${id}/edit`)}
            >
              Edit campaign gas units →
            </Button>
          </div>
        </section>
      )}

      {result && (
        <section
          data-testid={result.upload_log.rows_ingested > 0 ? UPLOAD.resultOk : UPLOAD.resultErrors}
          className="border border-border rounded-sm"
        >
          <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-secondary/40 flex items-center justify-between">
            <span>Ingest result</span>
            <span className="font-mono">
              {result.upload_log.rows_ingested} ingested · {result.upload_log.rows_skipped} skipped
            </span>
          </header>
          <div className="p-4 space-y-3">
            {/* The monitoring window, read from the file that defines it.
                Shown rather than merely applied: the window decides which
                readings a report is built from and what its capture
                percentage is, so it should never change without being
                seen. */}
            {result.upload_log.window_action === "set" && (
              <div className="flex items-start gap-2 text-sm">
                <CalendarCheck className="w-4 h-4 mt-0.5 text-primary shrink-0" />
                <span>
                  Monitoring window set from the file:{" "}
                  <span className="font-mono">
                    {fmtWindow(result.upload_log.data_start)} to{" "}
                    {fmtWindow(result.upload_log.data_end)}
                  </span>
                </span>
              </div>
            )}

            {result.upload_log.window_action === "differs" && (
              <div className="border border-amber-900/50 bg-amber-950/20 rounded-sm p-3 space-y-2">
                <p className="text-sm text-amber-300">
                  The window on this campaign does not match the file.
                </p>
                <p className="text-xs text-muted-foreground">
                  The file covers{" "}
                  <span className="font-mono">
                    {fmtWindow(result.upload_log.data_start)} to{" "}
                    {fmtWindow(result.upload_log.data_end)}
                  </span>. Nothing has been changed. A report built against a
                  window the data does not fall inside will have no readings
                  in it.
                </p>
                <div className="flex gap-2">
                  <Button size="sm" className="rounded-sm" disabled={adopting}
                          onClick={adoptWindow}>
                    {adopting && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
                    Use the file&rsquo;s dates
                  </Button>
                  <Button size="sm" variant="outline" className="rounded-sm"
                          onClick={() => nav(`/campaigns/${id}`)}>
                    Keep mine
                  </Button>
                </div>
              </div>
            )}

            {result.upload_log.rows_ingested > 0 && (
              <div className="flex items-center gap-2 text-emerald-400 text-sm">
                <CheckCircle2 className="w-4 h-4" />
                Successfully ingested {result.upload_log.rows_ingested} readings.
                <Button
                  variant="link"
                  className="text-primary p-0 h-auto ml-2"
                  onClick={() => nav(`/campaigns/${id}`)}
                >
                  View readings →
                </Button>
              </div>
            )}

            {Object.keys(unitsApplied).length > 0 && (
              <div data-testid="upload-units-applied">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">
                  Units applied to each gas
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(unitsApplied).map(([gas, applied]) => (
                    <span
                      key={gas}
                      className="text-[11px] font-mono border border-border text-muted-foreground rounded-sm px-1.5 py-0.5"
                      title="Unit read from the file's units row, the campaign's per-gas setting, or the older campaign-wide setting"
                    >
                      {gas} <span className="text-foreground">{applied}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(result.upload_log.recognized_columns?.length > 0 ||
              result.upload_log.ignored_columns?.length > 0) && (
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">
                    Recognized columns ({result.upload_log.recognized_columns?.length || 0})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(result.upload_log.recognized_columns || []).map((c) => (
                      <span
                        key={c}
                        className="text-[11px] font-mono border border-emerald-900 bg-emerald-950/30 text-emerald-300 rounded-sm px-1.5 py-0.5"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">
                    Ignored columns ({result.upload_log.ignored_columns?.length || 0})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(result.upload_log.ignored_columns || []).length === 0 ? (
                      <span className="text-[11px] text-muted-foreground">None</span>
                    ) : (
                      (result.upload_log.ignored_columns || []).map((c) => (
                        <span
                          key={c}
                          className="text-[11px] font-mono border border-border text-muted-foreground rounded-sm px-1.5 py-0.5"
                          title="Not part of the AAQ schema — dropped from ingest"
                        >
                          {c}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}

            {result.upload_log.auto_flagged_readings > 0 && (
              <div
                data-testid="upload-result-auto-flagged"
                className="border border-amber-900/60 bg-amber-950/20 rounded-sm p-3"
              >
                <div className="flex items-center gap-2 text-amber-300 text-sm">
                  <AlertTriangle className="w-4 h-4" />
                  <span>
                    Auto-flagged{" "}
                    <span className="font-mono">{result.upload_log.auto_flagged_readings}</span>{" "}
                    reading(s) with negative pollutant values — treated as instrument/calibration errors and
                    excluded from calculations.
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2 pl-6">
                  {Object.entries(result.upload_log.auto_flagged_field_counts || {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([field, count]) => (
                      <span
                        key={field}
                        className="text-[11px] font-mono border border-amber-800 text-amber-300 bg-amber-950/40 rounded-sm px-1.5 py-0.5"
                      >
                        {field} <span className="text-amber-400/80">× {count}</span>
                      </span>
                    ))}
                </div>
              </div>
            )}

            {result.upload_log.errors.length > 0 && (
              <div>
                <div className="flex items-center gap-2 text-amber-400 text-sm mb-2">
                  <AlertTriangle className="w-4 h-4" />
                  {result.upload_log.errors.length} note(s) and row error(s) — first 20 shown:
                </div>
                <ul className="text-xs font-mono space-y-0.5 max-h-60 overflow-auto border border-border rounded-sm p-2 bg-background/50">
                  {result.upload_log.errors.map((e, i) => (
                    <li key={i} className="text-red-300">• {e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
