import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Save } from "lucide-react";

import { createCampaign, getCampaign, updateCampaign } from "@/lib/api";
import { CAMPAIGN_FORM } from "@/constants/testIds";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const defaults = {
  project_name: "",
  client: "",
  provider: "Bander Said Allehiany (BSA)",
  site_name: "",
  latitude: "",
  longitude: "",
  inlet_height_m: 5.0,
  monitoring_start: "",
  monitoring_end: "",
  prepared_by: "",
  project_supervision: "",
  report_number: "",
  revision: "00",
  reporting_date: "",
};

// Convert ISO string → "YYYY-MM-DDTHH:mm" for <input type="datetime-local">.
function toLocalInput(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function toIsoDate(value) {
  if (!value) return "";
  return new Date(value).toISOString().slice(0, 10);
}

export default function CampaignForm({ mode }) {
  const { id } = useParams();
  const nav = useNavigate();
  const [form, setForm] = useState(defaults);
  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (mode !== "edit" || !id) return;
    (async () => {
      try {
        const c = await getCampaign(id);
        setForm({
          project_name: c.project_name || "",
          client: c.client || "",
          provider: c.provider || "",
          site_name: c.site_name || "",
          latitude: c.latitude ?? "",
          longitude: c.longitude ?? "",
          inlet_height_m: c.inlet_height_m ?? 5.0,
          monitoring_start: toLocalInput(c.monitoring_start),
          monitoring_end: toLocalInput(c.monitoring_end),
          prepared_by: c.prepared_by || "",
          project_supervision: c.project_supervision || "",
          report_number: c.report_number || "",
          revision: c.revision || "00",
          reporting_date: c.reporting_date ? toIsoDate(c.reporting_date) : "",
        });
      } catch {
        toast.error("Failed to load campaign");
      } finally {
        setLoading(false);
      }
    })();
  }, [mode, id]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        inlet_height_m: parseFloat(form.inlet_height_m),
        monitoring_start: new Date(form.monitoring_start).toISOString(),
        monitoring_end: new Date(form.monitoring_end).toISOString(),
        reporting_date: form.reporting_date
          ? new Date(form.reporting_date).toISOString()
          : null,
      };
      if (mode === "edit") {
        const updated = await updateCampaign(id, payload);
        toast.success("Campaign updated");
        nav(`/campaigns/${updated.id}`);
      } else {
        const created = await createCampaign(payload);
        toast.success("Campaign created");
        nav(`/campaigns/${created.id}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-sm text-muted-foreground">Loading…</div>;

  return (
    <form
      data-testid={CAMPAIGN_FORM.root}
      onSubmit={submit}
      className="space-y-6 max-w-4xl"
    >
      <header className="flex items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => nav(-1)}
          className="rounded-sm"
          data-testid={CAMPAIGN_FORM.cancelBtn}
        >
          <ArrowLeft className="w-4 h-4 mr-1" /> Back
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">
          {mode === "edit" ? "Edit Campaign" : "New Campaign"}
        </h1>
      </header>

      <Section title="Project">
        <Field label="Project name" required>
          <Input
            data-testid={CAMPAIGN_FORM.projectName}
            value={form.project_name}
            onChange={set("project_name")}
            required
            className="rounded-sm"
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Client" required>
            <Input
              data-testid={CAMPAIGN_FORM.client}
              value={form.client}
              onChange={set("client")}
              required
              className="rounded-sm"
            />
          </Field>
          <Field label="Provider / lab">
            <Input
              data-testid={CAMPAIGN_FORM.provider}
              value={form.provider}
              onChange={set("provider")}
              className="rounded-sm"
            />
          </Field>
        </div>
      </Section>

      <Section title="Site">
        <Field label="Site name" required>
          <Input
            data-testid={CAMPAIGN_FORM.siteName}
            value={form.site_name}
            onChange={set("site_name")}
            required
            className="rounded-sm"
          />
        </Field>
        <div className="grid grid-cols-3 gap-4">
          <Field label="Latitude (°N)" required>
            <Input
              data-testid={CAMPAIGN_FORM.latitude}
              value={form.latitude}
              onChange={set("latitude")}
              type="number"
              step="0.000001"
              required
              className="rounded-sm font-mono"
            />
          </Field>
          <Field label="Longitude (°E)" required>
            <Input
              data-testid={CAMPAIGN_FORM.longitude}
              value={form.longitude}
              onChange={set("longitude")}
              type="number"
              step="0.000001"
              required
              className="rounded-sm font-mono"
            />
          </Field>
          <Field label="Inlet height (m)">
            <Input
              data-testid={CAMPAIGN_FORM.inletHeight}
              value={form.inlet_height_m}
              onChange={set("inlet_height_m")}
              type="number"
              step="0.1"
              className="rounded-sm font-mono"
            />
          </Field>
        </div>
      </Section>

      <Section title="Monitoring window">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Start" required>
            <Input
              data-testid={CAMPAIGN_FORM.monitoringStart}
              type="datetime-local"
              value={form.monitoring_start}
              onChange={set("monitoring_start")}
              required
              className="rounded-sm font-mono"
            />
          </Field>
          <Field label="End" required>
            <Input
              data-testid={CAMPAIGN_FORM.monitoringEnd}
              type="datetime-local"
              value={form.monitoring_end}
              onChange={set("monitoring_end")}
              required
              className="rounded-sm font-mono"
            />
          </Field>
        </div>
      </Section>

      <Section title="Report metadata">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Prepared by">
            <Input
              data-testid={CAMPAIGN_FORM.preparedBy}
              value={form.prepared_by}
              onChange={set("prepared_by")}
              className="rounded-sm"
            />
          </Field>
          <Field label="Project supervision">
            <Input
              data-testid={CAMPAIGN_FORM.projectSupervision}
              value={form.project_supervision}
              onChange={set("project_supervision")}
              className="rounded-sm"
            />
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Field label="Report number">
            <Input
              data-testid={CAMPAIGN_FORM.reportNumber}
              value={form.report_number}
              onChange={set("report_number")}
              placeholder="BR-M200425-140"
              className="rounded-sm font-mono"
            />
          </Field>
          <Field label="Revision">
            <Input
              data-testid={CAMPAIGN_FORM.revision}
              value={form.revision}
              onChange={set("revision")}
              className="rounded-sm font-mono"
            />
          </Field>
          <Field label="Reporting date">
            <Input
              data-testid={CAMPAIGN_FORM.reportingDate}
              type="date"
              value={form.reporting_date}
              onChange={set("reporting_date")}
              className="rounded-sm font-mono"
            />
          </Field>
        </div>
      </Section>

      <div className="flex items-center justify-end gap-2 pt-2">
        <Button
          type="button"
          variant="ghost"
          onClick={() => nav(-1)}
          className="rounded-sm"
        >
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={saving}
          data-testid={CAMPAIGN_FORM.submitBtn}
          className="rounded-sm"
        >
          <Save className="w-4 h-4 mr-2" />
          {saving ? "Saving…" : mode === "edit" ? "Save changes" : "Create campaign"}
        </Button>
      </div>
    </form>
  );
}

function Section({ title, children }) {
  return (
    <section className="border border-border rounded-sm">
      <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-zinc-900/40">
        {title}
      </header>
      <div className="p-4 space-y-4">{children}</div>
    </section>
  );
}

function Field({ label, required, children }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </Label>
      {children}
    </div>
  );
}
