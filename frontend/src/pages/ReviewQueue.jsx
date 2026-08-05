import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  CheckCircle2, Eye, FileDown, Inbox, Loader2, RefreshCw, Undo2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import ReportViewer from "@/components/ReportViewer";
import {
  approveCampaign, downloadReportVersion, returnCampaign, reviewQueue,
} from "@/lib/api";

/**
 * The reviewing engineer's inbox.
 *
 * Before this existed, "a campaign was submitted" meant opening the campaign,
 * finding the Reports tab and guessing which of seventeen versions was the
 * one being signed off. Here the pinned version travels with the entry: who
 * sent it, when, which document, and a download button.
 */
function fmt(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export default function ReviewQueue() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState({});
  const [busy, setBusy] = useState(null);
  const [viewing, setViewing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await reviewQueue());
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load the queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = async (row, fn, okMessage, needsNote) => {
    const note = (notes[row.id] || "").trim();
    if (needsNote && !note) {
      toast.error("Say what needs changing — the engineer sees this comment.");
      return;
    }
    setBusy(row.id);
    try {
      await fn(row.id, note);
      toast.success(okMessage);
      setNotes((n) => ({ ...n, [row.id]: "" }));
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not complete that");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      {viewing && (
        <ReportViewer report={viewing} onClose={() => setViewing(null)} />
      )}

      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
          <Inbox className="w-5 h-5 text-primary" /> Review
          <Badge variant="outline" className="rounded-sm font-mono">
            {rows.length}
          </Badge>
        </h1>
        <Button
          variant="outline" size="icon" className="rounded-sm h-9 w-9 ml-auto"
          onClick={load} title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </p>
      ) : rows.length === 0 ? (
        <div className="border border-border rounded-sm p-10 text-center">
          <p className="text-sm text-muted-foreground">
            Nothing waiting for review.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => (
            <section key={r.id} className="border border-border rounded-sm">
              <header className="px-4 py-3 border-b border-border flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <Link
                  to={`/campaigns/${r.id}`}
                  className="text-sm font-semibold hover:underline"
                >
                  {r.project_name || "Untitled campaign"}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {r.client || "—"}
                  {r.site_name ? ` · ${r.site_name}` : ""}
                  {r.report_number ? ` · ${r.report_number}` : ""}
                </span>
                <span className="ml-auto text-xs text-muted-foreground">
                  Submitted by{" "}
                  <span className="text-foreground">{r.submitted_by || "—"}</span>
                  {" · "}{fmt(r.submitted_at)}
                </span>
              </header>

              <div className="px-4 py-3">
                {r.report ? (
                  <div className="flex flex-wrap items-center gap-3 border border-border rounded-sm bg-secondary/30 px-3 py-2">
                    <Badge variant="outline" className="rounded-sm font-mono">
                      {r.report.version
                        ? `v${String(r.report.version).padStart(3, "0")}`
                        : "—"}
                    </Badge>
                    <span className="text-xs uppercase text-muted-foreground">
                      {(r.report.lang || "en")} · {(r.report.format || "docx")}
                    </span>
                    <span className="text-xs font-mono truncate max-w-[420px]">
                      {r.report.filename}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {r.report.size_bytes
                        ? `${(r.report.size_bytes / 1048576).toFixed(1)} MB`
                        : ""}
                    </span>
                    <div className="ml-auto flex items-center gap-2">
                      <Button
                        variant="outline" className="rounded-sm h-9"
                        onClick={() => setViewing(r.report)}
                      >
                        <Eye className="w-4 h-4 mr-1.5" /> Read
                      </Button>
                      <Button
                        className="rounded-sm h-9"
                        onClick={() =>
                          downloadReportVersion(r.report.id, r.report.filename)
                            .catch((e) =>
                              toast.error(
                                e?.response?.status === 410
                                  ? "That file is no longer on the server — ask for it to be regenerated."
                                  : "Download failed"
                              )
                            )
                        }
                      >
                        <FileDown className="w-4 h-4 mr-1.5" /> Download
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No report version was attached to this submission.
                  </p>
                )}

                {r.newer_version_exists && (
                  <p className="text-[11px] text-muted-foreground mt-2">
                    A newer version has been generated since this was
                    submitted. You are reviewing the version above.
                  </p>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Input
                    value={notes[r.id] || ""}
                    onChange={(e) =>
                      setNotes((n) => ({ ...n, [r.id]: e.target.value }))
                    }
                    placeholder="Comment (required when returning, optional when approving)"
                    className="rounded-sm h-9 text-sm flex-1 min-w-[240px]"
                  />
                  <Button
                    className="rounded-sm h-9"
                    disabled={busy === r.id}
                    onClick={() =>
                      act(r, approveCampaign, "Campaign approved", false)
                    }
                  >
                    <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approve
                  </Button>
                  <Button
                    variant="outline" className="rounded-sm h-9"
                    disabled={busy === r.id}
                    onClick={() =>
                      act(r, returnCampaign, "Sent back to the engineer", true)
                    }
                  >
                    <Undo2 className="w-4 h-4 mr-1.5" /> Return
                  </Button>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
