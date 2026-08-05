import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Copy, FileText, FileDown, Loader2, History, Link2, RefreshCw, ScrollText,
  Trash2, Send, CheckCircle2, Undo2, Lock, Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import ReportPreview from "@/components/ReportPreview";
import ReportViewer from "@/components/ReportViewer";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  approveCampaign, campaignAudit, createShare, downloadReportVersion,
  generateReport, getCampaign, isAdmin, listReports, listShares,
  returnCampaign, revokeShare, shareUrl, submitForReview,
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
  const [sharing, setSharing] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [days, setDays] = useState(30);
  const [newLink, setNewLink] = useState(null);
  const [preview, setPreview] = useState(false);

  // Who is signed in decides what this panel offers. The server enforces it
  // regardless — see routes/review.py.
  const admin = isAdmin();
  const [status, setStatus] = useState(null);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  // Which stored version is open in the on-screen reader, if any.
  const [viewing, setViewing] = useState(null);
  // Which generated version is being submitted. A campaign accumulates many;
  // "this campaign is ready" tells the reviewer nothing about which document
  // they are signing off.
  const [submitVersion, setSubmitVersion] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const c = await getCampaign(campaignId);
      setStatus(c);
    } catch {
      /* the panel still works without it */
    }
  }, [campaignId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const runReview = async (fn, okMessage, needsNote) => {
    const note = reviewNote.trim();
    if (needsNote && !note) {
      toast.error("Say what needs changing — the operator sees this comment.");
      return;
    }
    setReviewBusy(true);
    try {
      await fn(campaignId, note, submitVersion || undefined);
      toast.success(okMessage);
      setReviewNote("");
      loadStatus();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not complete that");
    } finally {
      setReviewBusy(false);
    }
  };

  const makeShare = async () => {
    setSharing(true);
    try {
      const s = await createShare({
        campaign_id: campaignId, recipient: recipient || null,
        days_valid: days,
      });
      setNewLink(shareUrl(s.token));
      setRecipient("");
      toast.success("Client link created");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create the link");
    } finally {
      setSharing(false);
    }
  };

  const withdraw = async (id) => {
    if (!window.confirm("Withdraw this link? The client will lose access immediately."))
      return;
    try {
      await revokeShare(id);
      toast.success("Link withdrawn");
      refresh();
    } catch {
      toast.error("Could not withdraw the link");
    }
  };
  const [reports, setReports] = useState([]);
  const [audit, setAudit] = useState([]);
  const [shares, setShares] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [r, a, sh] = await Promise.all([
        listReports(campaignId),
        campaignAudit(campaignId),
        listShares(campaignId).catch(() => []),
      ]);
      setReports(r);
      // Newest first from the API — default to it, so the ordinary case
      // needs no thought, but leave the choice visible.
      setSubmitVersion((cur) =>
        cur && r.some((x) => x.id === cur) ? cur : (r[0]?.id || ""));
      setAudit(a);
      setShares(sh);
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
      const out = await generateReport(campaignId, lang, format);
      if (out.downloaded) {
        toast.success(`Report ready: ${out.filename}`);
      } else {
        // Operator: the report exists and is listed below, but the file
        // itself is released by the reviewing engineer.
        toast.success(
          `Report generated (v${String(out.version || "").padStart(3, "0")}). ` +
          "Use Preview to check it, then Submit for review."
        );
      }
      refresh();
      loadStatus();
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      toast.error(`Report generation failed: ${detail}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {viewing && (
        <ReportViewer report={viewing} onClose={() => setViewing(null)} />
      )}
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
            variant="outline"
            className="rounded-sm h-9"
            onClick={() => setPreview((v) => !v)}
            data-testid="preview-toggle"
          >
            {preview ? "Hide preview" : "Preview"}
          </Button>
          <Button
            onClick={onGenerate}
            disabled={busy}
            className="rounded-sm h-9"
            data-testid="generate-report-btn"
          >
            {busy ? (
              <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Generating…</>
            ) : (
              admin
                ? <><FileDown className="w-4 h-4 mr-1.5" /> Generate & download</>
                : <><FileText className="w-4 h-4 mr-1.5" /> Generate</>
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
        {preview && (
          <div className="mt-4 pt-4 border-t border-border">
            <ReportPreview
              campaignId={campaignId}
              onGenerate={() => { setPreview(false); onGenerate(); }}
              onClose={() => setPreview(false)}
            />
          </div>
        )}
      </div>

      {/* Review workflow */}
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Send className="w-4 h-4 text-primary" /> Review
          {status?.status && (
            <Badge variant="outline" className="rounded-sm font-mono uppercase">
              {status.status}
            </Badge>
          )}
        </h3>

        {status?.review_comment && (
          <div className="mt-3 border-l-2 border-primary bg-secondary/40 px-3 py-2 rounded-sm">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {status.status === "approved" ? "Approved with note" : "Returned by the reviewer"}
            </div>
            <p className="text-xs mt-1">{status.review_comment}</p>
          </div>
        )}

        {status?.status === "submitted" ? (
          <>
            <p className="text-xs text-muted-foreground mt-2">
              Submitted by {status.submitted_by || "—"}
              {status.submitted_at ? ` · ${fmtTs(status.submitted_at)}` : ""}
              {admin ? " — waiting for you." : " — waiting for the reviewing engineer."}
            </p>
            {(() => {
              const sent = reports.find((r) => r.id === status.submitted_report_id);
              if (!sent) return null;
              return (
                <div className="mt-2 flex flex-wrap items-center gap-2 border border-border rounded-sm bg-secondary/30 px-3 py-2">
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Under review
                  </span>
                  <Badge variant="outline" className="rounded-sm font-mono">
                    {sent.version ? `v${String(sent.version).padStart(3, "0")}` : "—"}
                  </Badge>
                  <span className="text-xs uppercase text-muted-foreground">
                    {(sent.lang || "en")} · {(sent.format || "docx")}
                  </span>
                  <span className="text-xs font-mono truncate max-w-[360px]">
                    {sent.filename}
                  </span>
                  {reports[0] && reports[0].id !== sent.id && (
                    <span className="text-[11px] text-muted-foreground w-full">
                      A newer version exists. Submit again to put that one
                      under review instead.
                    </span>
                  )}
                </div>
              );
            })()}
          </>
        ) : (
          <p className="text-xs text-muted-foreground mt-1">
            {admin
              ? "Sign the campaign off, or send it back with a note. Returning it puts the campaign back to ready so it can be corrected and resubmitted."
              : "When the campaign is complete, send it to the reviewing engineer. You can keep editing after submitting — the report is rebuilt from the current readings."}
          </p>
        )}

        <div className="mt-3 space-y-2">
          <Input
            value={reviewNote}
            onChange={(e) => setReviewNote(e.target.value)}
            placeholder={admin
              ? "Comment (required when returning, optional when approving)"
              : "Note for the reviewer (optional)"}
            className="rounded-sm h-9 text-sm"
            data-testid="review-note"
          />
          <div className="flex flex-wrap items-center gap-2">
            {admin ? (
              <>
                <Button
                  onClick={() => runReview(approveCampaign, "Campaign approved", false)}
                  disabled={reviewBusy}
                  className="rounded-sm h-9"
                  data-testid="approve-btn"
                >
                  <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approve
                </Button>
                <Button
                  variant="outline"
                  onClick={() => runReview(returnCampaign, "Sent back to the operator", true)}
                  disabled={reviewBusy}
                  className="rounded-sm h-9"
                  data-testid="return-btn"
                >
                  <Undo2 className="w-4 h-4 mr-1.5" /> Return with comment
                </Button>
              </>
            ) : (
              <>
                <Select value={submitVersion} onValueChange={setSubmitVersion}>
                  <SelectTrigger className="w-[280px] rounded-sm h-9"
                                 data-testid="submit-version">
                    <SelectValue placeholder={
                      reports.length ? "Choose a version" : "Generate a report first"
                    } />
                  </SelectTrigger>
                  <SelectContent>
                    {reports.map((r) => (
                      <SelectItem key={r.id} value={r.id}>
                        {r.version ? `v${String(r.version).padStart(3, "0")}` : "—"}
                        {" · "}{(r.lang || "en").toUpperCase()}
                        {" · "}{(r.format || "docx").toUpperCase()}
                        {" · "}{fmtTs(r.generated_at)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              <Button
                onClick={() => runReview(submitForReview, "Sent for review", false)}
                // Locked only when the chosen version is the one already
                // waiting. Submitting a newer version is how a correction
                // reaches the reviewer.
                disabled={reviewBusy || !submitVersion
                          || (status?.status === "submitted"
                              && status?.submitted_report_id === submitVersion)}
                className="rounded-sm h-9"
                data-testid="submit-review-btn"
              >
                {reviewBusy
                  ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Sending…</>
                  : <><Send className="w-4 h-4 mr-1.5" />
                      {status?.status === "submitted"
                        ? "Resubmit this version"
                        : "Submit for review"}</>}
              </Button>
              </>
            )}
          </div>
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
                <TableHead className="text-xs">Read</TableHead>
                <TableHead className="text-xs text-right">
                  {admin ? "Download" : "File"}
                </TableHead>
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
                  <TableCell>
                    {r.id && (
                      <button
                        onClick={() => setViewing(r)}
                        className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                        data-testid="view-report-btn"
                      >
                        <Eye className="w-3.5 h-3.5" /> View
                      </button>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {!admin ? (
                      <span className="text-xs text-muted-foreground inline-flex items-center gap-1"
                            title="Downloads are released by the reviewing engineer">
                        <Lock className="w-3 h-3" /> {r.filename}
                      </span>
                    ) : r.id ? (
                      <button
                        onClick={() =>
                          downloadReportVersion(r.id, r.filename).catch((e) =>
                            toast.error(
                              e?.response?.status === 410
                                ? "This file is no longer on the server — regenerate to create a new version."
                                : "Download failed"
                            )
                          )
                        }
                        className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                      >
                        <FileDown className="w-3.5 h-3.5" /> {r.filename}
                      </button>
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


      {/* Client share links — admin only: the link downloads the report
          with no login, so it is the same privilege as downloading. */}
      {admin && (
      <div className="border border-border rounded-sm p-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Link2 className="w-4 h-4 text-primary" /> Client links
          <Badge variant="outline" className="rounded-sm font-mono">
            {shares.filter((s) => !s.revoked && !s.expired).length}
          </Badge>
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          A private, read-only page where the client can download this
          project's reports without an account. Links expire and can be
          withdrawn at any time.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Input
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
            placeholder="Recipient (optional, for your records)"
            className="rounded-sm h-9 max-w-xs text-xs"
          />
          <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="w-[130px] rounded-sm h-9 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
              <SelectItem value="365">1 year</SelectItem>
            </SelectContent>
          </Select>
          <Button className="rounded-sm h-9" onClick={makeShare} disabled={sharing}>
            {sharing ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                     : <Link2 className="w-4 h-4 mr-1.5" />}
            Create link
          </Button>
        </div>

        {newLink && (
          <div className="mt-3 border border-primary/40 bg-primary/5 rounded-sm p-3">
            <p className="text-xs text-muted-foreground mb-1.5">
              Copy this now — it is shown only once.
            </p>
            <div className="flex items-center gap-2">
              <code className="text-xs break-all flex-1">{newLink}</code>
              <Button variant="outline" size="sm" className="rounded-sm h-8"
                      onClick={() => {
                        navigator.clipboard?.writeText(newLink);
                        toast.success("Link copied");
                      }}>
                <Copy className="w-3.5 h-3.5 mr-1" /> Copy
              </Button>
            </div>
          </div>
        )}

        {shares.length > 0 && (
          <ul className="mt-3 divide-y divide-border">
            {shares.map((s) => (
              <li key={s.id} className="py-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="min-w-0">
                  {s.recipient || "Unnamed recipient"}
                  <span className="text-muted-foreground">
                    {" · "}{s.views || 0} views · {s.downloads || 0} downloads
                  </span>
                </span>
                <span className="ml-auto">
                  {s.revoked ? (
                    <span className="text-muted-foreground">withdrawn</span>
                  ) : s.expired ? (
                    <span className="text-amber-500">expired</span>
                  ) : (
                    <span className="text-emerald-500">active</span>
                  )}
                </span>
                {!s.revoked && (
                  <Button variant="ghost" size="sm" className="rounded-sm h-7"
                          onClick={() => withdraw(s.id)}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      )}

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
