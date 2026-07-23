import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity, AlertCircle, ArrowRight, FileText, FolderOpen, Loader2, Plus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { homeDashboard } from "@/lib/api";

const when = (t) => {
  if (!t) return "—";
  const d = new Date(t);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} h ago`;
  return d.toLocaleDateString();
};

const ACTIONS = {
  "campaign.create": "created a campaign",
  "campaign.update": "updated a campaign",
  "campaign.delete": "deleted a campaign",
  "readings.upload": "uploaded readings",
  "readings.clear": "cleared readings",
  "reading.flag": "changed a reading",
  "report.generate": "generated a report",
  "share.create": "shared a report",
  "share.revoke": "withdrew a share link",
  "user.create": "added a user",
  "user.update": "updated a user",
  "station.create": "added a mobile lab",
  "station.update": "updated a mobile lab",
  "attachment.upload": "uploaded attachments",
};

function Stat({ label, value, to }) {
  const body = (
    <div className="bg-secondary/50 rounded-sm p-4 hover:bg-secondary transition-colors">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold mt-0.5 tabular">{value}</div>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function HomeDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    homeDashboard().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">Nothing to show yet.</p>;
  }

  const { counts, recent_campaigns = [], recent_reports = [],
          needs_attention = [], activity = [] } = data;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Everything in flight across your monitoring projects.
          </p>
        </div>
        <Button asChild className="rounded-sm h-9">
          <Link to="/campaigns/new">
            <Plus className="w-4 h-4 mr-1.5" /> New campaign
          </Link>
        </Button>
      </header>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Campaigns" value={counts.campaigns} to="/campaigns" />
        <Stat label="With data" value={counts.with_data} />
        <Stat label="Reported" value={counts.reported} />
        <Stat label="Reports generated" value={counts.reports} />
      </div>

      {needs_attention.length > 0 && (
        <div className="border border-amber-500/40 bg-amber-500/5 rounded-sm p-4">
          <h2 className="text-sm font-semibold flex items-center gap-2 text-amber-500">
            <AlertCircle className="w-4 h-4" /> Needs attention
          </h2>
          <ul className="mt-2.5 divide-y divide-border">
            {needs_attention.map((c) => (
              <li key={c.id} className="py-2 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <Link to={`/campaigns/${c.id}`}
                        className="text-sm hover:underline truncate block">
                    {c.project_name}
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    {c.client} · {c.reason}
                  </span>
                </div>
                <Button asChild variant="ghost" size="sm" className="rounded-sm h-8">
                  <Link to={`/campaigns/${c.id}`}>
                    Open <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="border border-border rounded-sm p-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-primary" /> Recent campaigns
          </h2>
          {recent_campaigns.length === 0 ? (
            <p className="text-xs text-muted-foreground mt-3">
              No campaigns yet — create your first one.
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-border">
              {recent_campaigns.map((c) => (
                <li key={c.id} className="py-2">
                  <Link to={`/campaigns/${c.id}`}
                        className="text-sm hover:underline">{c.project_name}</Link>
                  <div className="flex flex-wrap items-center gap-1.5 mt-1">
                    <span className="text-xs text-muted-foreground">
                      {c.client} · {c.site_name}
                    </span>
                    {c.has_report ? (
                      <Badge variant="outline" className="rounded-sm text-[10px] text-emerald-500">
                        reported
                      </Badge>
                    ) : c.has_data ? (
                      <Badge variant="outline" className="rounded-sm text-[10px] text-amber-500">
                        data ready
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="rounded-sm text-[10px]">
                        no data
                      </Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="border border-border rounded-sm p-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" /> Recent reports
          </h2>
          {recent_reports.length === 0 ? (
            <p className="text-xs text-muted-foreground mt-3">
              No reports generated yet.
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-border">
              {recent_reports.map((r) => (
                <li key={r.id || r.filename} className="py-2">
                  <Link to={`/campaigns/${r.campaign_id}`}
                        className="text-sm hover:underline">
                    {r.project_name || "Report"}
                  </Link>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    v{String(r.version || 1).padStart(3, "0")} ·{" "}
                    {(r.lang || "en").toUpperCase()} ·{" "}
                    {(r.format || "docx").toUpperCase()} · {when(r.generated_at)}
                    {r.generated_by ? ` · ${r.generated_by}` : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="border border-border rounded-sm p-4">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" /> Recent activity
        </h2>
        {activity.length === 0 ? (
          <p className="text-xs text-muted-foreground mt-3">No activity yet.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {activity.map((a) => (
              <li key={a.id} className="text-xs flex flex-wrap gap-x-1.5">
                <span className="font-medium">{a.user}</span>
                <span className="text-muted-foreground">
                  {ACTIONS[a.action] || a.action}
                </span>
                <span className="text-muted-foreground/70 ml-auto">
                  {when(a.timestamp)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
