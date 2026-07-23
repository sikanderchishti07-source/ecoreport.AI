import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, Check, ChevronLeft, ChevronRight, FileText, Loader2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import AttachmentsPanel from "@/components/AttachmentsPanel";
import InstrumentsPanel from "@/components/InstrumentsPanel";
import ReportPreview from "@/components/ReportPreview";
import {
  createCampaign, generateReport, getCampaign, listReadings, uploadReadings,
} from "@/lib/api";

const STEPS = [
  { key: "details", label: "Campaign details" },
  { key: "data", label: "Upload data" },
  { key: "instruments", label: "Instruments" },
  { key: "attachments", label: "Photos & certificates" },
  { key: "review", label: "Review & generate" },
];

const BLANK = {
  project_name: "", client: "", site_name: "",
  latitude: "", longitude: "", inlet_height_m: 5,
  gas_units: "ugm3", monitoring_start: "", monitoring_end: "",
  prepared_by: "", project_supervision: "", report_number: "", revision: "00",
};

function Stepper({ index }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 mb-6">
      {STEPS.map((s, i) => {
        const done = i < index;
        const active = i === index;
        return (
          <li key={s.key} className="flex items-center gap-2">
            <span className={`w-6 h-6 rounded-full inline-flex items-center justify-center text-[11px] font-semibold ${
              done ? "bg-emerald-500 text-white"
                : active ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground"}`}>
              {done ? <Check className="w-3.5 h-3.5" /> : i + 1}
            </span>
            <span className={`text-xs ${active ? "font-medium" : "text-muted-foreground"}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default function CampaignWizard() {
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(BLANK);
  const [campaign, setCampaign] = useState(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);
  const [uploadLog, setUploadLog] = useState(null);
  const [readingCount, setReadingCount] = useState(0);

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target?.value ?? e }));

  const refreshCampaign = useCallback(async () => {
    if (!campaign?.id) return;
    try {
      const c = await getCampaign(campaign.id);
      setCampaign(c);
    } catch { /* keep the current copy */ }
  }, [campaign?.id]);

  useEffect(() => { refreshCampaign(); }, [step, refreshCampaign]);

  const createIt = async () => {
    setBusy(true);
    try {
      const payload = {
        ...form,
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
        inlet_height_m: Number(form.inlet_height_m) || 5,
        monitoring_start: new Date(form.monitoring_start).toISOString(),
        monitoring_end: new Date(form.monitoring_end).toISOString(),
      };
      const c = await createCampaign(payload);
      setCampaign(c);
      toast.success("Campaign created");
      setStep(1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create the campaign");
    } finally {
      setBusy(false);
    }
  };

  const doUpload = async () => {
    if (!file) return toast.error("Choose a file first");
    setBusy(true);
    try {
      const res = await uploadReadings(campaign.id, file);
      setUploadLog(res.upload_log);
      const rs = await listReadings(campaign.id, { limit: 1 });
      setReadingCount(res.upload_log?.rows_ingested || rs.length);
      toast.success(`${res.upload_log.rows_ingested} rows ingested`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    try {
      const name = await generateReport(campaign.id, "en", "docx");
      toast.success(`Report ready: ${name}`);
      nav(`/campaigns/${campaign.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setBusy(false);
    }
  };

  const canNext =
    step === 0 ? form.project_name && form.client && form.site_name &&
                 form.latitude && form.longitude &&
                 form.monitoring_start && form.monitoring_end
    : step === 1 ? readingCount > 0
    : true;

  return (
    <div className="space-y-6 max-w-4xl">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">New campaign</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Five steps from site details to a finished report.
        </p>
      </header>

      <Stepper index={step} />

      {/* 1 — details */}
      {step === 0 && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="space-y-1.5 md:col-span-2">
              <Label className="text-xs">Project name *</Label>
              <Input className="rounded-sm h-9" value={form.project_name}
                     onChange={set("project_name")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Client *</Label>
              <Input className="rounded-sm h-9" value={form.client}
                     onChange={set("client")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Site name *</Label>
              <Input className="rounded-sm h-9" value={form.site_name}
                     onChange={set("site_name")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Latitude *</Label>
              <Input className="rounded-sm h-9" value={form.latitude}
                     onChange={set("latitude")} placeholder="24.7136" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Longitude *</Label>
              <Input className="rounded-sm h-9" value={form.longitude}
                     onChange={set("longitude")} placeholder="46.6753" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Monitoring start *</Label>
              <Input type="datetime-local" className="rounded-sm h-9"
                     value={form.monitoring_start} onChange={set("monitoring_start")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Monitoring end *</Label>
              <Input type="datetime-local" className="rounded-sm h-9"
                     value={form.monitoring_end} onChange={set("monitoring_end")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Gas data units *</Label>
              <Select value={form.gas_units}
                      onValueChange={(v) => setForm((f) => ({ ...f, gas_units: v }))}>
                <SelectTrigger className="rounded-sm h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ugm3">µg/m³ (already converted)</SelectItem>
                  <SelectItem value="ppb">ppb — convert on upload</SelectItem>
                  <SelectItem value="ppm">ppm — convert on upload</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Report number</Label>
              <Input className="rounded-sm h-9" value={form.report_number}
                     onChange={set("report_number")} placeholder="BR-Q010426-001" />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            The monitoring window must cover the timestamps in your data file —
            the next step will tell you if it doesn’t.
          </p>
        </div>
      )}

      {/* 2 — data */}
      {step === 1 && campaign && (
        <div className="space-y-4">
          <div className="border border-border rounded-sm p-4">
            <Label className="text-xs">Monitoring data (CSV or Excel)</Label>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <Input type="file" accept=".csv,.xls,.xlsx"
                     className="rounded-sm h-9 max-w-sm"
                     onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <Button className="rounded-sm h-9" onClick={doUpload} disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null}
                Upload
              </Button>
            </div>
          </div>
          {uploadLog && (
            <div className="border border-border rounded-sm p-4 space-y-2">
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge variant="outline" className="rounded-sm">
                  {uploadLog.rows_ingested} rows ingested
                </Badge>
                {uploadLog.rows_skipped > 0 && (
                  <Badge variant="outline" className="rounded-sm">
                    {uploadLog.rows_skipped} skipped
                  </Badge>
                )}
                {uploadLog.auto_flagged_readings > 0 && (
                  <Badge variant="outline" className="rounded-sm text-amber-500">
                    {uploadLog.auto_flagged_readings} auto-flagged
                  </Badge>
                )}
              </div>
              {(uploadLog.errors || []).slice(0, 6).map((m, i) => (
                <p key={i} className="text-xs text-muted-foreground flex gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-500" />
                  {m}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3 — instruments */}
      {step === 2 && campaign && (
        <InstrumentsPanel campaign={campaign} onSaved={refreshCampaign} />
      )}

      {/* 4 — attachments */}
      {step === 3 && campaign && <AttachmentsPanel campaign={campaign} />}

      {/* 5 — review */}
      {step === 4 && campaign && (
        <ReportPreview
          campaignId={campaign.id}
          onGenerate={generate}
          onClose={() => setStep(3)}
        />
      )}

      <div className="flex items-center gap-2 pt-2">
        {step > 0 && (
          <Button variant="outline" className="rounded-sm h-9"
                  onClick={() => setStep((s) => s - 1)}>
            <ChevronLeft className="w-4 h-4 mr-1" /> Back
          </Button>
        )}
        {step === 0 ? (
          <Button className="rounded-sm h-9" onClick={createIt}
                  disabled={!canNext || busy}>
            {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null}
            Create and continue
          </Button>
        ) : step < STEPS.length - 1 ? (
          <Button className="rounded-sm h-9" onClick={() => setStep((s) => s + 1)}
                  disabled={!canNext}>
            Continue <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        ) : null}
        {step > 0 && campaign && (
          <Button variant="ghost" className="rounded-sm h-9 ml-auto"
                  onClick={() => nav(`/campaigns/${campaign.id}`)}>
            <FileText className="w-4 h-4 mr-1.5" /> Open campaign
          </Button>
        )}
      </div>
    </div>
  );
}
