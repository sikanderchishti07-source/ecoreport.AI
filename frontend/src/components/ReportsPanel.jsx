import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  FileText, FileDown, Loader2, History, RefreshCw, ScrollText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  campaignAudit, generateReport, listReports, reportDownloadUrl,
} from "@/lib/api";

const LANGS = [
  { value: "en", label: "English" },
  { value: "ar", label: "العربية (Arabic)" },
  { value: "bilingual", label: "Bilingual (EN + AR)" },
];
const FORMATS = [
  { value: "docx", label: "Word (DOCX)" },
  { value: "pdf", label: "PDF" },
];

const ACTION_LABELS = {
  "campaign.create": "Campaign created",
  "campaign.update": "Campaign updated",
  "campaign.delete": "Campaign deleted",
  "readings.upload": "Readings uploaded",
  "readings.clear": "Readings cleared",
  "reading.flag": "Reading validity changed",
  "report.generate": "Report generated",
};

function fmtTs(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function AuditDetails({ entry }) {
  const d = entry.details || {};
  if (entry.action === "campaign.update" && d.changes) {
    return (
      <span className="text-muted-foreground">
        {Object.entries(d.changes)
          .map(([k, v]) => `${k}: ${v.from ?? "—"} → ${v.to ?? "—"}`)
          .join("; ")}
      </span>
    );
  }
  if (entry.action === "readings.upload") {
    return (
      <span className="text-muted-foreground">
        {d.filename} — {d.rows_ingested} rows ingested
        {d.auto_flagged_readings ? `, ${d.auto_flagged_readings} auto-flagged` : ""}
      </span>
    );
  }
  if (entry.action === "reading.flag") {
    return (
      <span className="text-muted-foreground">
        {d.timestamp} → {d.valid_to ? "valid" : `invalid (${d.reason || "no reason"})`}
      </span>
    );
  }
  if (entry.action === "report.generate") {
    return (
      <span className="text-muted-foreground">
        v{String(d.version).padStart(3, "0")} · {d.lang} · {d.format}
      </span>
    );
  }
  if (entry.action === "readings.clear") {
    return <span className="text-muted-foreground">{d.rows_deleted} rows deleted</span>;
  }
  return null;
}

export default function ReportsPanel({ campaignId, readingCount }) {
  const [lang, setLang] = useState("en");
  const [format, setFormat] = useState("docx");
  const [busy, setBusy] = useState(false);
  const [reports, setReports] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [r, a] = await Promise.all([
        listReports(campaignId),
        campaignAudit(campaignId),
      ]);
      setReports(r);
      setAudit(a);
    } catch (e) {
      toast.error("Failed to load report history");
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onGenerate = async () => {
    if (!readingCount) {
      toast.error("Upload monitoring readings before generating a report.");
      return;
    }
    setBusy(true);
    const label = `${LANGS.find((l) => l.value === lang)?.label} ${format.toUpperCase()}`;
    toast.info(`Generating ${label} report — this can take a minute…`);
    try {
      const fname = await generateReport(campaignId, lang, format);
      toast.success(`Report ready: ${fname}`);
      refresh();
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      toast.error(`Report generation failed: ${detail}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Generate */}
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" /> Generate report
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Builds the full AAQ report from the current validated readings —
          every graph and table is recalculated on each run. Each run is saved
          as a new version below.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Select value={lang} onValueChange={setLang}>
            <SelectTrigger className="w-[190px] rounded-sm h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGS.map((l) => (
                <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={format} onValueChange={setFormat}>
            <SelectTrigger className="w-[150px] rounded-sm h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FORMATS.map((f) => (
                <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={onGenerate}
            disabled={busy}
            className="rounded-sm h-9"
            data-testid="generate-report-btn"
          >
            {busy ? (
              <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Generating…</>
            ) : (
              <><FileDown className="w-4 h-4 mr-1.5" /> Generate & download</>
            )}
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="rounded-sm h-9 w-9 ml-auto"
            onClick={refresh}
            title="Refresh history"
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Version history */}
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <History className="w-4 h-4 text-primary" /> Version history
          <Badge variant="outline" className="rounded-sm font-mono">
            {reports.length}
          </Badge>
        </h3>
        {loading ? (
          <p className="text-xs text-muted-foreground mt-3">Loading…</p>
        ) : reports.length === 0 ? (
          <p className="text-xs text-muted-foreground mt-3">
            No reports generated yet.
          </p>
        ) : (
          <Table className="mt-2">
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Version</TableHead>
                <TableHead className="text-xs">Language</TableHead>
                <TableHead className="text-xs">Format</TableHead>
                <TableHead className="text-xs">Generated</TableHead>
                <TableHead className="text-xs">By</TableHead>
                <TableHead className="text-xs text-right">Download</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.map((r) => (
                <TableRow key={r.id || r.filename}>
                  <TableCell className="font-mono text-xs">
                    {r.version ? `v${String(r.version).padStart(3, "0")}` : "—"}
                  </TableCell>
                  <TableCell className="text-xs uppercase">{r.lang || "en"}</TableCell>
                  <TableCell className="text-xs uppercase">{r.format || "docx"}</TableCell>
                  <TableCell className="text-xs">{fmtTs(r.generated_at)}</TableCell>
                  <TableCell className="text-xs">{r.generated_by || "—"}</TableCell>
                  <TableCell className="text-right">
                    {r.id ? (
                      <a
                        href={reportDownloadUrl(r.id)}
                        className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                      >
                        <FileDown className="w-3.5 h-3.5" /> {r.filename}
                      </a>
                    ) : (
                      <span className="text-xs text-muted-foreground">{r.filename}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Activity / audit trail */}
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <ScrollText className="w-4 h-4 text-primary" /> Activity log
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Complete audit trail for this campaign — uploads, data validation
          changes, edits, and report generations.
        </p>
        {loading ? (
          <p className="text-xs text-muted-foreground mt-3">Loading…</p>
        ) : audit.length === 0 ? (
          <p className="text-xs text-muted-foreground mt-3">No activity recorded yet.</p>
        ) : (
          <ul className="mt-3 space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {audit.map((e) => (
              <li
                key={e.id}
                className="text-xs border border-border rounded-sm px-3 py-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5"
              >
                <span className="font-mono text-muted-foreground whitespace-nowrap">
                  {fmtTs(e.timestamp)}
                </span>
                <Badge variant="outline" className="rounded-sm">
                  {ACTION_LABELS[e.action] || e.action}
                </Badge>
                <span className="font-medium">{e.user}</span>
                <AuditDetails entry={e} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
