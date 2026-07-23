import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Activity, Download, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { portalDownloadUrl, portalView } from "@/lib/api";

const fmtDate = (t) =>
  t ? new Date(t).toLocaleDateString(undefined,
        { day: "numeric", month: "short", year: "numeric" }) : "—";

const fmtSize = (b) =>
  !b ? "" : b > 1048576 ? `${(b / 1048576).toFixed(1)} MB`
                        : `${Math.round(b / 1024)} KB`;

export default function PortalPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    portalView(token)
      .then(setData)
      .catch((e) => setError(
        e?.response?.data?.detail || "This link could not be opened."))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="max-w-3xl mx-auto px-5 py-4 flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-7 h-7 border border-border rounded-sm">
            <Activity className="w-4 h-4 text-primary" />
          </span>
          <span className="text-sm font-semibold tracking-tight">
            Ambient Air Quality Monitoring
          </span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-8">
        {loading && (
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Opening…
          </p>
        )}

        {error && !loading && (
          <div className="border border-border rounded-sm p-6 text-center">
            <p className="text-sm">{error}</p>
            <p className="text-xs text-muted-foreground mt-2">
              Please contact the consultancy for an up-to-date link.
            </p>
          </div>
        )}

        {data && (
          <>
            <h1 className="text-2xl font-semibold tracking-tight">
              {data.project.name}
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Prepared for {data.project.client} by {data.provider.name}
            </p>

            <dl className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6 border border-border rounded-sm p-4 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">Site</dt>
                <dd>{data.project.site || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Report number</dt>
                <dd>{data.project.report_number || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Monitoring period</dt>
                <dd>
                  {fmtDate(data.project.monitoring_start)} – {fmtDate(data.project.monitoring_end)}
                </dd>
              </div>
            </dl>

            <h2 className="text-sm font-semibold mt-8 mb-2 flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary" /> Reports
            </h2>

            {data.reports.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No reports have been published for this project yet.
              </p>
            ) : (
              <ul className="border border-border rounded-sm divide-y divide-border">
                {data.reports.map((r) => (
                  <li key={r.id}
                      className="p-3.5 flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm">
                        Version {String(r.version || 1).padStart(3, "0")} ·{" "}
                        {(r.lang || "en").toUpperCase()} ·{" "}
                        {(r.format || "docx").toUpperCase()}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {fmtDate(r.generated_at)} {fmtSize(r.size_bytes)}
                      </div>
                    </div>
                    <Button asChild variant="outline" className="rounded-sm h-9">
                      <a href={portalDownloadUrl(token, r.id)}>
                        <Download className="w-4 h-4 mr-1.5" /> Download
                      </a>
                    </Button>
                  </li>
                ))}
              </ul>
            )}

            <p className="text-xs text-muted-foreground mt-6">
              This link is private and expires on {fmtDate(data.expires_at)}.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
