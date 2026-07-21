import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Trash2, ArrowRight, MapPin, Search, X } from "lucide-react";

import { listCampaigns, deleteCampaign, searchArchive } from "@/lib/api";
import { CAMPAIGNS_LIST } from "@/constants/testIds";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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

const statusVariant = {
  draft: "bg-zinc-800 text-muted-foreground border-border",
  ingested: "bg-sky-950/50 text-sky-300 border-sky-900",
  ready: "bg-emerald-950/40 text-emerald-300 border-emerald-900",
  archived: "bg-zinc-900 text-muted-foreground border-border",
};

function StatusPill({ value }) {
  const cls = statusVariant[value] || statusVariant.draft;
  return (
    <span className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-[11px] uppercase tracking-wider ${cls}`}>
      {value}
    </span>
  );
}

function formatWindow(start, end) {
  try {
    const s = new Date(start);
    const e = new Date(end);
    const opts = { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" };
    return `${s.toLocaleString(undefined, opts)} → ${e.toLocaleString(undefined, opts)}`;
  } catch {
    return `${start} → ${end}`;
  }
}

export default function CampaignsList() {
  const nav = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [searchMeta, setSearchMeta] = useState(null); // {count, reports}

  const load = async () => {
    setLoading(true);
    try {
      const data = await listCampaigns();
      setCampaigns(data);
    } catch (err) {
      toast.error("Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Server-side archive search (project, client, site, report number)
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setSearchMeta(null);
      load();
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await searchArchive(q);
        const reportInfo = {};
        data.results.forEach((r) => {
          reportInfo[r.campaign.id] = {
            count: r.report_count,
            latest: r.latest_report,
          };
        });
        setCampaigns(data.results.map((r) => r.campaign));
        setSearchMeta({ count: data.count, reports: reportInfo });
      } catch {
        toast.error("Search failed");
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const handleDelete = async (id) => {
    try {
      await deleteCampaign(id);
      toast.success("Campaign deleted");
      load();
    } catch (err) {
      toast.error("Delete failed");
    }
  };

  return (
    <div data-testid={CAMPAIGNS_LIST.root} className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Each campaign is one AAQ monitoring project — client, site, and monitoring window.
          </p>
        </div>
        <Button
          data-testid={CAMPAIGNS_LIST.createBtn}
          onClick={() => nav("/campaigns/new")}
          className="rounded-sm"
        >
          <Plus className="w-4 h-4 mr-2" /> New Campaign
        </Button>
      </header>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 border border-border rounded-sm px-3 h-10 bg-zinc-900/40 w-full max-w-md">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search archive — project, client, site, or report number…"
            className="bg-transparent outline-none text-sm w-full placeholder:text-muted-foreground"
            data-testid="archive-search-input"
          />
          {query && (
            <button onClick={() => setQuery("")} title="Clear">
              <X className="w-4 h-4 text-muted-foreground hover:text-foreground" />
            </button>
          )}
        </div>
        {searchMeta && (
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {searchMeta.count} match{searchMeta.count === 1 ? "" : "es"}
          </span>
        )}
      </div>

      <section className="border border-border rounded-sm overflow-hidden">
        <div className="grid grid-cols-12 bg-zinc-900/50 text-[11px] uppercase tracking-wider text-muted-foreground px-4 py-2 border-b border-border">
          <div className="col-span-4">Project</div>
          <div className="col-span-3">Client</div>
          <div className="col-span-3">Monitoring window</div>
          <div className="col-span-1 text-right font-mono">Rows</div>
          <div className="col-span-1 text-right">Actions</div>
        </div>

        {loading && (
          <div className="px-4 py-10 text-sm text-muted-foreground">Loading…</div>
        )}

        {!loading && campaigns.length === 0 && (
          <div
            data-testid={CAMPAIGNS_LIST.emptyState}
            className="px-4 py-14 text-center text-sm text-muted-foreground"
          >
            No campaigns yet. Create your first monitoring campaign to begin.
          </div>
        )}

        {!loading && campaigns.map((c) => (
          <div
            key={c.id}
            data-testid={CAMPAIGNS_LIST.row(c.id)}
            className="grid grid-cols-12 px-4 py-3 border-b border-border last:border-b-0 items-center hover:bg-zinc-900/40 transition-colors"
          >
            <div className="col-span-4">
              <div className="flex items-center gap-2 font-medium">
                <span>{c.project_name}</span>
                <StatusPill value={c.status} />
              </div>
              <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                <MapPin className="w-3 h-3" />
                <span className="font-mono tabular">
                  {c.latitude.toFixed(6)}, {c.longitude.toFixed(6)}
                </span>
                <span>· {c.site_name}</span>
              </div>
            </div>
            <div className="col-span-3 text-sm truncate">{c.client}</div>
            <div className="col-span-3 text-xs font-mono tabular text-muted-foreground truncate">
              {formatWindow(c.monitoring_start, c.monitoring_end)}
            </div>
            <div className="col-span-1 text-right font-mono tabular text-sm">
              {c.reading_count}
            </div>
            <div className="col-span-1 flex items-center justify-end gap-1">
              <Button
                variant="ghost"
                size="sm"
                data-testid={CAMPAIGNS_LIST.rowOpen(c.id)}
                onClick={() => nav(`/campaigns/${c.id}`)}
                className="rounded-sm"
              >
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    data-testid={CAMPAIGNS_LIST.rowDelete(c.id)}
                    className="rounded-sm text-red-400 hover:text-red-300"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent className="rounded-sm">
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this campaign?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This removes the campaign, its readings, and its upload history.
                      This cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel className="rounded-sm">Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => handleDelete(c.id)}
                      className="rounded-sm bg-red-600 hover:bg-red-500"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
