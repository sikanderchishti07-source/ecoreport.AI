import { useEffect, useState } from "react";
import {
  AlertTriangle, CheckCircle2, FileText, Loader2, XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { previewReport } from "@/lib/api";

const LABELS = {
  SO2: "SO₂", NO2: "NO₂", NOx: "NOₓ", NO: "NO", CO: "CO",
  O3: "O₃", H2S: "H₂S", PM10: "PM10", PM25: "PM2.5",
};

const num = (v, d = 1) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(d);

export default function ReportPreview({ campaignId, onGenerate, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    previewReport(campaignId)
      .then(setData)
      .catch((e) => setError(e?.response?.data?.detail || "Preview failed"))
      .finally(() => setLoading(false));
  }, [campaignId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6">
        <Loader2 className="w-4 h-4 animate-spin" /> Checking what the report
        will contain…
      </div>
    );
  }

  if (error) {
    return (
      <div className="border border-border rounded-sm p-4">
        <p className="text-sm text-red-500">{error}</p>
        <Button variant="outline" className="rounded-sm h-8 mt-3" onClick={onClose}>
          Close
        </Button>
      </div>
    );
  }

  const { ready, blockers = [], warnings = [], campaign, headline,
          pollutants = [], sections = [] } = data;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" /> Report preview
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            What the document will say, before it is built.
          </p>
        </div>
        {ready ? (
          <Badge className="rounded-sm bg-emerald-500/15 text-emerald-500 border-0">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Can be generated
          </Badge>
        ) : (
          <Badge className="rounded-sm bg-red-500/15 text-red-500 border-0">
            <XCircle className="w-3.5 h-3.5 mr-1" /> Cannot be generated
          </Badge>
        )}
      </div>

      {blockers.map((b, i) => (
        <div key={i} className="border border-red-500/40 bg-red-500/10 rounded-sm p-3">
          <p className="text-xs text-red-500 flex gap-2">
            <XCircle className="w-4 h-4 shrink-0" /> {b}
          </p>
        </div>
      ))}

      {warnings.length > 0 && (
        <div className="border border-amber-500/40 bg-amber-500/10 rounded-sm p-3">
          <p className="text-xs font-semibold text-amber-500 flex items-center gap-1.5 mb-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Worth checking first
          </p>
          <ul className="space-y-1">
            {warnings.map((w, i) => (
              <li key={i} className="text-xs text-amber-500/90">• {w}</li>
            ))}
          </ul>
        </div>
      )}

      {campaign && (
        <div className="border border-border rounded-sm p-3 grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
          <div><span className="text-muted-foreground">Project</span><br />{campaign.project_name}</div>
          <div><span className="text-muted-foreground">Client</span><br />{campaign.client}</div>
          <div><span className="text-muted-foreground">Site</span><br />{campaign.site_name}</div>
          <div><span className="text-muted-foreground">Window</span><br />{campaign.window}</div>
          <div><span className="text-muted-foreground">Report no.</span><br />{campaign.report_number || "—"}</div>
          <div><span className="text-muted-foreground">Revision</span><br />{campaign.revision}</div>
        </div>
      )}

      {headline && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          {[
            ["Monitoring hours", headline.monitoring_hours],
            ["Data capture", `${headline.capture_pct}%`],
            ["Exceedances", headline.exceedances],
            ["Instruments", headline.instruments],
          ].map(([k, v]) => (
            <div key={k} className="bg-secondary/50 rounded-sm p-3">
              <div className="text-[11px] text-muted-foreground">{k}</div>
              <div className="text-lg font-semibold tabular">{v}</div>
            </div>
          ))}
        </div>
      )}

      {pollutants.length > 0 && (
        <div className="border border-border rounded-sm overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Pollutant</TableHead>
                <TableHead className="text-xs text-right">Capture</TableHead>
                <TableHead className="text-xs text-right">Max</TableHead>
                <TableHead className="text-xs text-right">Mean</TableHead>
                <TableHead className="text-xs">Verdict</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pollutants.map((p) => {
                const bad = p.periods.some((e) => e.verdict === "non-compliant");
                const low = p.capture_pct < 75;
                return (
                  <TableRow key={p.pollutant}>
                    <TableCell className="text-xs">
                      {LABELS[p.pollutant] || p.pollutant}
                      {p.supporting && (
                        <span className="text-muted-foreground"> (supporting)</span>
                      )}
                    </TableCell>
                    <TableCell className={`text-xs text-right tabular ${
                      low ? "text-amber-500" : ""}`}>
                      {p.capture_pct}%
                    </TableCell>
                    <TableCell className="text-xs text-right tabular">
                      {p.mdl && p.max !== null && p.max < p.mdl
                        ? `<${num(p.mdl)}` : num(p.max)}
                    </TableCell>
                    <TableCell className="text-xs text-right tabular">
                      {num(p.mean)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {p.supporting ? (
                        <span className="text-muted-foreground">no limit</span>
                      ) : bad ? (
                        <span className="text-red-500">exceedance</span>
                      ) : low ? (
                        <span className="text-amber-500">N/R*</span>
                      ) : (
                        <span className="text-emerald-500">compliant</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {sections.length > 0 && (
        <div className="border border-border rounded-sm p-3">
          <p className="text-xs font-semibold mb-2">Document structure</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
            {sections.map((s) => (
              <div key={s.title} className="flex justify-between text-xs">
                <span>{s.title}</span>
                <span className="text-muted-foreground">
                  {s.figures} fig · {s.tables} tbl
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <Button className="rounded-sm h-9" disabled={!ready}
                onClick={onGenerate} data-testid="preview-generate-btn">
          <FileText className="w-4 h-4 mr-1.5" /> Generate this report
        </Button>
        <Button variant="outline" className="rounded-sm h-9" onClick={onClose}>
          Back
        </Button>
      </div>
    </div>
  );
}
