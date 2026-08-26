import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Download, FileText, Loader2, Search, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  deleteReports, downloadReportVersion, listClients, listReportArchive,
} from "@/lib/api";

const TYPE_LABEL = { air: "Air", noise: "Noise", soil_water: "Soil & water" };
const ANY = "__any";

const STATUS_STYLE = {
  approved: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  in_review: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  submitted: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  draft: "bg-secondary text-muted-foreground border-border",
};

function fmtDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
  return d.toLocaleDateString(undefined,
    { day: "2-digit", month: "short", year: "numeric" });
}

function fmtSize(bytes) {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

/**
 * The last twelve months the archive actually contains, newest first. Built
 * from the reports rather than from the calendar, so the filter never offers
 * a month with nothing in it.
 */
function monthsIn(reports) {
  const seen = new Map();
  for (const r of reports) {
    const key = String(r.generated_at || "").slice(0, 7);
    if (!key || seen.has(key)) continue;
    const d = new Date(`${key}-01T00:00:00Z`);
    seen.set(key, Number.isNaN(d.getTime()) ? key
      : d.toLocaleDateString(undefined, { month: "long", year: "numeric" }));
  }
  return [...seen.entries()].sort((a, b) => b[0].localeCompare(a[0]));
}

export default function ReportsPage() {
  const nav = useNavigate();
  const [data, setData] = useState({ reports: [], stats: {}, count: 0, total: 0 });
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(null);
  // Selection is by report id, not by row index: the list re-sorts and
  // re-filters underneath, and an index would silently point at a different
  // report after either.
  const [selected, setSelected] = useState(() => new Set());
  const [deleting, setDeleting] = useState(false);

  const [q, setQ] = useState("");
  const [clientId, setClientId] = useState(ANY);
  const [type, setType] = useState(ANY);
  const [month, setMonth] = useState(ANY);

  // Every filter is applied server-side so the counts and the rows always
  // describe the same set. Debounced because it re-queries on each keystroke.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (q.trim()) params.q = q.trim();
      if (clientId !== ANY) params.client_id = clientId;
      if (type !== ANY) params.campaign_type = type;
      if (month !== ANY) params.month = month;
      setData(await listReportArchive(params));
    } catch {
      toast.error("Could not load reports");
    } finally {
      setLoading(false);
    }
  }, [q, clientId, type, month]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  // Filters change what is on screen, so a selection made before the change
  // would delete reports the operator can no longer see.
  useEffect(() => { setSelected(new Set()); }, [q, clientId, type, month]);

  useEffect(() => {
    listClients().then(setClients).catch(() => setClients([]));
  }, []);

  // Months come from the unfiltered archive, so choosing one does not empty
  // the list it was chosen from.
  const [allMonths, setAllMonths] = useState([]);
  useEffect(() => {
    listReportArchive({}).then((d) => setAllMonths(monthsIn(d.reports || [])))
      .catch(() => setAllMonths([]));
  }, []);

  // downloadReportVersion already fetches, names and saves the file; this
  // only reports failure, since a blob error body is not readable as JSON
  // without decoding it first.
  const download = async (r) => {
    setDownloading(r.id);
    try {
      await downloadReportVersion(r.id, r.filename || `report.${r.format}`);
    } catch (err) {
      let detail = "Could not download";
      try {
        const b = err?.response?.data;
        if (b && typeof b.text === "function") {
          detail = JSON.parse(await b.text()).detail || detail;
        }
      } catch { /* keep the generic message */ }
      toast.error(detail);
    } finally {
      setDownloading(null);
    }
  };

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    const visible = data.reports.map((r) => r.id);
    const allOn = visible.length > 0 && visible.every((id) => selected.has(id));
    setSelected(allOn ? new Set() : new Set(visible));
  };

  const removeSelected = async (includeApproved = false) => {
    const ids = [...selected];
    if (!ids.length) return;
    if (!includeApproved
        && !window.confirm(`Delete ${ids.length} report version(s)? `
                           + "The files are removed as well and this cannot "
                           + "be undone.")) {
      return;
    }
    setDeleting(true);
    try {
      const out = await deleteReports(ids, includeApproved);
      toast.success(`${out.deleted} report(s) deleted`);
      if (out.file_warnings?.length) {
        toast.info("Some files were already missing and could not be removed.");
      }
      setSelected(new Set());
      await load();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      // 409 means approved reports were in the selection. The server stopped
      // rather than deleting them, so the second confirmation is a real
      // decision and not a formality.
      if (err?.response?.status === 409 && detail) {
        if (window.confirm(`${detail}\n\nDelete them as well?`)) {
          await removeSelected(true);
          return;
        }
      } else {
        toast.error(detail || "Could not delete");
      }
    } finally {
      setDeleting(false);
    }
  };

  const stats = data.stats || {};
  const filtered = useMemo(
    () => q.trim() || clientId !== ANY || type !== ANY || month !== ANY,
    [q, clientId, type, month],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" /> Reports
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Every report issued, across every campaign. Each version is listed
          separately — a revision does not hide the one it replaced.
        </p>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          ["Total issued", stats.total ?? 0, ""],
          ["This month", stats.this_month ?? 0, ""],
          ["In review", stats.in_review ?? 0, "text-amber-400"],
          ["Approved", stats.approved ?? 0, "text-emerald-400"],
        ].map(([label, value, tone]) => (
          <div key={label} className="border border-border rounded-sm p-3">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            <p className={`text-xl font-medium mt-0.5 ${tone}`}>{value}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="rounded-sm pl-9"
                 placeholder="Report number, project, client or site…"
                 value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select value={clientId} onValueChange={setClientId}>
          <SelectTrigger className="rounded-sm w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>All clients</SelectItem>
            {clients.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.short_name || c.legal_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="rounded-sm w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>All types</SelectItem>
            <SelectItem value="air">Air</SelectItem>
            <SelectItem value="noise">Noise</SelectItem>
            <SelectItem value="soil_water">Soil &amp; water</SelectItem>
          </SelectContent>
        </Select>
        <Select value={month} onValueChange={setMonth}>
          <SelectTrigger className="rounded-sm w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any month</SelectItem>
            {allMonths.map(([key, label]) => (
              <SelectItem key={key} value={key}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {filtered && (
        <p className="text-xs text-muted-foreground -mt-2">
          Showing {data.count} of {data.total}.
          <button className="ml-2 underline"
                  onClick={() => { setQ(""); setClientId(ANY); setType(ANY); setMonth(ANY); }}>
            Clear filters
          </button>
        </p>
      )}

      {selected.size > 0 && (
        <div className="flex items-center justify-between gap-3 flex-wrap
                        border border-border rounded-sm px-4 py-2.5 -mt-2">
          <span className="text-sm">
            {selected.size} selected
            <button className="ml-3 text-xs underline text-muted-foreground"
                    onClick={() => setSelected(new Set())}>
              Clear
            </button>
          </span>
          <Button variant="outline" size="sm" disabled={deleting}
                  className="rounded-sm text-red-400 hover:text-red-300"
                  onClick={() => removeSelected(false)}>
            {deleting
              ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              : <Trash2 className="w-3.5 h-3.5 mr-1.5" />}
            Delete
          </Button>
        </div>
      )}

      <div className="border border-border rounded-sm overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]">
          <thead>
            <tr className="bg-secondary/50 text-muted-foreground text-xs">
              <th className="w-10 px-3 py-2">
                <input
                  type="checkbox"
                  aria-label="Select every report shown"
                  checked={data.reports.length > 0
                           && data.reports.every((r) => selected.has(r.id))}
                  onChange={toggleAll}
                />
              </th>
              <th className="text-left px-4 py-2 font-normal">Report</th>
              <th className="text-left px-4 py-2 font-normal">Client</th>
              <th className="text-left px-4 py-2 font-normal">Issued</th>
              <th className="text-left px-4 py-2 font-normal">Status</th>
              <th className="text-right px-4 py-2 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin inline mr-2" /> Loading…
              </td></tr>
            )}
            {!loading && data.reports.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground text-sm">
                {data.total === 0
                  ? "No reports have been generated yet."
                  : "No reports match those filters."}
              </td></tr>
            )}
            {!loading && data.reports.map((r) => (
              <tr key={r.id}
                  className={`border-t border-border ${
                    selected.has(r.id) ? "bg-secondary/40" : ""}`}>
                <td className="px-3 py-3 align-top">
                  <input
                    type="checkbox"
                    aria-label={`Select ${r.report_number} version ${r.version}`}
                    checked={selected.has(r.id)}
                    onChange={() => toggle(r.id)}
                  />
                </td>
                <td className="px-4 py-3">
                  <div className="font-mono text-xs">{r.report_number}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {r.project_name}
                    {r.campaign_type ? ` · ${TYPE_LABEL[r.campaign_type] || r.campaign_type}` : ""}
                    {` · v${r.version} · ${String(r.format).toUpperCase()}`}
                    {r.size_bytes ? ` · ${fmtSize(r.size_bytes)}` : ""}
                  </div>
                  {r.campaign_deleted && (
                    <div className="text-[11px] text-amber-400 mt-0.5">
                      The campaign behind this report has been deleted.
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">{r.client}</td>
                <td className="px-4 py-3">
                  {fmtDate(r.generated_at)}
                  <div className="text-xs text-muted-foreground">{r.generated_by}</div>
                </td>
                <td className="px-4 py-3">
                  <Badge variant="outline"
                         className={`rounded-sm text-[10px] uppercase ${STATUS_STYLE[r.status] || STATUS_STYLE.draft}`}>
                    {String(r.status).replace(/_/g, " ")}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" className="rounded-sm"
                            disabled={downloading === r.id}
                            onClick={() => download(r)}>
                      {downloading === r.id
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <Download className="w-3.5 h-3.5" />}
                    </Button>
                    {!r.campaign_deleted && (
                      <Button variant="ghost" size="sm" className="rounded-sm text-xs"
                              onClick={() => nav(`/campaigns/${r.campaign_id}`)}>
                        Open
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground">
        Downloads are available to reviewing engineers. Where a campaign is
        linked to a client record, the client&rsquo;s recorded legal name is
        shown; otherwise the name typed on the campaign is used.
      </p>
    </div>
  );
}
