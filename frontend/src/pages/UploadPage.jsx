import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, UploadCloud, FileSpreadsheet, CheckCircle2, AlertTriangle } from "lucide-react";

import { getCampaign, uploadReadings } from "@/lib/api";
import { UPLOAD } from "@/constants/testIds";
import { Button } from "@/components/ui/button";

const REQUIRED = ["timestamp"];
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

  const submit = async () => {
    if (!file) {
      toast.error("Choose a file first");
      return;
    }
    setUploading(true);
    try {
      const res = await uploadReadings(id, file);
      setResult(res);
      if (res.upload_log.rows_ingested > 0) {
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

      <section className="border border-border rounded-sm">
        <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-zinc-900/40">
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
          <div>• Pollutants: µg/m³ · Temp: °C · RH: % · Pressure: hPa · Wind speed: m/s · Wind direction: ° (0–360)</div>
          <div>• Cadence: 1 row per hour · Timestamps: ISO-8601 (YYYY-MM-DD HH:MM:SS)</div>
          <div>• QA flag is not read from the file — mark rows as invalid via the Readings tab after upload.</div>
        </div>
      </section>

      <label
        htmlFor="upload-input"
        data-testid={UPLOAD.dropzone}
        data-active={dragActive}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        className="dropzone block rounded-sm p-10 text-center cursor-pointer bg-zinc-900/20"
      >
        <UploadCloud className="w-8 h-8 mx-auto text-muted-foreground" />
        <p className="mt-3 text-sm">
          <span className="text-primary underline decoration-dotted">Click to browse</span>{" "}
          or drop a .csv / .xlsx file here
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

      {result && (
        <section
          data-testid={result.upload_log.rows_ingested > 0 ? UPLOAD.resultOk : UPLOAD.resultErrors}
          className="border border-border rounded-sm"
        >
          <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-zinc-900/40 flex items-center justify-between">
            <span>Ingest result</span>
            <span className="font-mono">
              {result.upload_log.rows_ingested} ingested · {result.upload_log.rows_skipped} skipped
            </span>
          </header>
          <div className="p-4 space-y-3">
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
            {result.upload_log.errors.length > 0 && (
              <div>
                <div className="flex items-center gap-2 text-amber-400 text-sm mb-2">
                  <AlertTriangle className="w-4 h-4" />
                  {result.upload_log.errors.length} row error(s) — first 20 shown:
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
