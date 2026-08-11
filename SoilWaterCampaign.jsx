import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowLeft, Check, ChevronRight, FlaskConical, Loader2,
  Plus, Trash2, Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  createCampaign, createLabSample, deleteLabSample, getCampaign,
  getLandUseComparison, getSampleReadiness, getSampleSettings,
  getSampleSummary, ingestResultsCsv, listAnalytes, listLabSamples,
  listParameterProfiles, listSampleStandards, saveSampleSettings,
  updateLabSample,
} from "@/lib/api";

const STEPS = [
  { key: "details", label: "Campaign details" },
  { key: "scope", label: "Standard & parameters" },
  { key: "samples", label: "Samples" },
  { key: "results", label: "Results" },
  { key: "review", label: "Review" },
];

const BLANK_CAMPAIGN = {
  project_name: "", client: "", site_name: "",
  latitude: "", longitude: "",
  monitoring_start: "", monitoring_end: "",
  prepared_by: "", project_supervision: "", report_number: "", revision: "00",
};

const BLANK_CONTEXT = {
  particle_size: null, land_use: null, depth: null,
  water_medium: null, discharge_destination: null, is_single_sample: true,
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

/**
 * The context that selects the limit. Kept visually separate and captioned,
 * because it is the single field most likely to be wrong and least likely to
 * be noticed — a soil result judged against the natural-area column when the
 * site is commercial reads as entirely correct on the page.
 */
function ContextFields({ standard, options, value, onChange }) {
  const set = (k, v) => onChange({ ...value, [k]: v === "__unset" ? null : v });
  const isSoil = standard === "ncec_soil" || standard === "ads_81_2017";
  const isAmbient = standard === "ncec_water_ambient";
  const isDischarge = standard === "ncec_water_discharge";
  if (!isSoil && !isAmbient && !isDischarge) return null;

  const field = (label, key, items, hint) => (
    <div>
      <Label className="text-xs">{label}</Label>
      <Select value={value[key] || "__unset"} onValueChange={(v) => set(key, v)}>
        <SelectTrigger className="rounded-sm mt-1">
          <SelectValue placeholder="Not stated" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__unset">Not stated</SelectItem>
          {(items || []).map((o) => (
            <SelectItem key={o.key} value={o.key}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hint && <p className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
    </div>
  );

  return (
    <div className="border border-border rounded-sm p-4 bg-secondary/20">
      <div className="flex items-start gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          These choose every limit in the report. Left unstated, results are
          printed with no compliance conclusion rather than judged against a
          guessed column.
        </p>
      </div>
      <div className="grid sm:grid-cols-3 gap-3">
        {isSoil && field("Soil particle size", "particle_size",
          options.particle_sizes, "Grains at or above 75 µm are coarse.")}
        {isSoil && field("Land use", "land_use", options.land_uses,
          "Five columns in Appendix 1; they differ widely.")}
        {isSoil && field("Sampling depth", "depth", options.depths,
          "Applies to the hydrocarbon rows.")}
        {isAmbient && field("Water body class", "water_medium",
          options.water_media,
          "All coastal water is public unless declared otherwise.")}
        {isDischarge && field("Discharge destination", "discharge_destination",
          options.discharge_destinations)}
      </div>
    </div>
  );
}

export default function SoilWaterCampaign() {
  const nav = useNavigate();
  const { id: routeId } = useParams();
  const [search] = useSearchParams();

  const [step, setStep] = useState(routeId ? 1 : 0);
  const [busy, setBusy] = useState(false);
  const [campaignId, setCampaignId] = useState(routeId || null);
  const [campaign, setCampaign] = useState(null);
  const [form, setForm] = useState(BLANK_CAMPAIGN);

  const [options, setOptions] = useState(null);
  const [analytes, setAnalytes] = useState([]);
  const [groups, setGroups] = useState([]);
  const [profiles, setProfiles] = useState([]);

  const [settings, setSettings] = useState({
    medium: "soil", standard: "none", decision_rule: "simple_acceptance",
    analyte_keys: [], profile_id: null, laboratory: "",
    lab_accreditation: "", default_context: BLANK_CONTEXT,
  });

  const [samples, setSamples] = useState([]);
  const [newSample, setNewSample] = useState({ code: "", label: "" });
  const [file, setFile] = useState(null);
  const [ingest, setIngest] = useState(null);
  const [summary, setSummary] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [comparison, setComparison] = useState(null);

  // The medium is chosen, not inferred. A campaign is one medium and one
  // report — soil samples and water samples from the same site are two
  // separate campaigns, because they are two separate issued reports.
  const medium = settings.medium || "soil";
  const mediumInfo = useMemo(
    () => (options?.media || []).find((m) => m.key === medium) || null,
    [options, medium],
  );
  const allowedStandards = useMemo(() => {
    if (!options) return [];
    const allowed = mediumInfo?.standards || [];
    return options.standards.filter((s) => allowed.includes(s.key));
  }, [options, mediumInfo]);

  useEffect(() => {
    (async () => {
      try {
        setOptions(await listSampleStandards());
      } catch {
        toast.error("Could not load the standards list");
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await listAnalytes(medium);
        setAnalytes(data.analytes || []);
        setGroups(data.groups || []);
        setProfiles(await listParameterProfiles({ medium }));
      } catch {
        toast.error("Could not load the parameter library");
      }
    })();
  }, [medium]);

  const loadCampaign = useCallback(async (cid) => {
    const [c, s, list] = await Promise.all([
      getCampaign(cid), getSampleSettings(cid), listLabSamples(cid),
    ]);
    setCampaign(c);
    setSettings({
      ...s,
      medium: s.medium || "soil",
      laboratory: s.laboratory || "",
      lab_accreditation: s.lab_accreditation || "",
      default_context: { ...BLANK_CONTEXT, ...(s.default_context || {}) },
    });
    setSamples(list);
  }, []);

  useEffect(() => {
    if (!campaignId) return;
    loadCampaign(campaignId).catch(() => toast.error("Could not load the campaign"));
  }, [campaignId, loadCampaign]);

  const refreshReview = useCallback(async (cid) => {
    const [sum, ready] = await Promise.all([
      getSampleSummary(cid), getSampleReadiness(cid),
    ]);
    setSummary(sum);
    setReadiness(ready);
    try {
      setComparison(await getLandUseComparison(cid));
    } catch {
      setComparison(null);
    }
  }, []);

  const handleCreate = async () => {
    setBusy(true);
    try {
      const payload = {
        ...form,
        campaign_type: "soil_water",
        latitude: parseFloat(form.latitude) || 0,
        longitude: parseFloat(form.longitude) || 0,
        // monitoring_end is required at creation; a guessed window would
        // look real and could reach a report, so it mirrors the start until
        // someone sets it deliberately.
        monitoring_start: form.monitoring_start,
        monitoring_end: form.monitoring_end || form.monitoring_start,
      };
      const created = await createCampaign(payload);
      setCampaignId(created.id);
      setCampaign(created);
      toast.success("Campaign created");
      setStep(1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create the campaign");
    } finally {
      setBusy(false);
    }
  };

  const persistSettings = async (next) => {
    if (!campaignId) return;
    setBusy(true);
    try {
      const payload = {
        ...next,
        medium: next.medium || "soil",
        laboratory: next.laboratory || null,
        lab_accreditation: next.lab_accreditation || null,
      };
      const saved = await saveSampleSettings(campaignId, payload);
      setSettings({
        ...saved,
        medium: saved.medium || "soil",
        laboratory: saved.laboratory || "",
        lab_accreditation: saved.lab_accreditation || "",
        default_context: { ...BLANK_CONTEXT, ...(saved.default_context || {}) },
      });
      toast.success("Saved");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  const toggleAnalyte = (key) => {
    const keys = settings.analyte_keys.includes(key)
      ? settings.analyte_keys.filter((k) => k !== key)
      : [...settings.analyte_keys, key];
    setSettings({ ...settings, analyte_keys: keys, profile_id: null });
  };

  const applyProfile = (profileId) => {
    const p = profiles.find((x) => x.id === profileId);
    if (!p) return;
    setSettings({ ...settings, analyte_keys: [...p.analyte_keys], profile_id: p.id });
    toast.success(`${p.analyte_keys.length} parameters selected`);
  };

  const addSample = async () => {
    if (!newSample.code.trim()) {
      toast.error("A sample code is required");
      return;
    }
    setBusy(true);
    try {
      await createLabSample(campaignId, {
        campaign_id: campaignId,
        code: newSample.code.trim(),
        label: newSample.label.trim(),
        // The server sets the medium from the campaign; sending one here
        // would only be a second source of truth to disagree with it.
        medium,
        context: BLANK_CONTEXT,
      });
      setNewSample({ code: "", label: "" });
      setSamples(await listLabSamples(campaignId));
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not add the sample");
    } finally {
      setBusy(false);
    }
  };

  const removeSample = async (sampleId) => {
    try {
      await deleteLabSample(sampleId);
      setSamples(await listLabSamples(campaignId));
    } catch {
      toast.error("Could not delete the sample");
    }
  };

  const saveSampleContext = async (sample, context) => {
    try {
      await updateLabSample(sample.id, { context });
      setSamples(await listLabSamples(campaignId));
    } catch {
      toast.error("Could not save the sample context");
    }
  };

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const rep = await ingestResultsCsv(campaignId, file);
      setIngest(rep);
      setSamples(await listLabSamples(campaignId));
      toast.success(`${rep.values_stored} results stored`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const goReview = async () => {
    setBusy(true);
    try {
      await refreshReview(campaignId);
      setStep(4);
    } catch {
      toast.error("Could not evaluate the campaign");
    } finally {
      setBusy(false);
    }
  };

  const selected = new Set(settings.analyte_keys);
  const grouped = groups
    .map((g) => ({ ...g, items: analytes.filter((a) => a.group === g.key) }))
    .filter((g) => g.items.length);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-primary" />
            {mediumInfo?.title || "Soil & water campaign"}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {campaign
              ? `${campaign.project_name} — ${campaign.client}`
              : "Laboratory results for soil, water or sediment samples."}
          </p>
        </div>
        <Button variant="ghost" className="rounded-sm"
                onClick={() => nav("/campaigns")}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Campaigns
        </Button>
      </header>

      <Stepper index={step} />

      {/* ---------------- 0. details ---------------- */}
      {step === 0 && (
        <section className="border border-border rounded-sm p-5 space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            {[
              ["project_name", "Project name"],
              ["client", "Client"],
              ["site_name", "Site name"],
              ["report_number", "Report number"],
              ["prepared_by", "Prepared by"],
              ["project_supervision", "Supervision"],
            ].map(([key, label]) => (
              <div key={key}>
                <Label className="text-xs">{label}</Label>
                <Input className="rounded-sm mt-1" value={form[key]}
                       onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
              </div>
            ))}
            <div>
              <Label className="text-xs">Latitude</Label>
              <Input className="rounded-sm mt-1" value={form.latitude}
                     onChange={(e) => setForm({ ...form, latitude: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">Longitude</Label>
              <Input className="rounded-sm mt-1" value={form.longitude}
                     onChange={(e) => setForm({ ...form, longitude: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">Sampling date</Label>
              <Input type="datetime-local" className="rounded-sm mt-1"
                     value={form.monitoring_start}
                     onChange={(e) => setForm({ ...form, monitoring_start: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">Reporting date</Label>
              <Input type="datetime-local" className="rounded-sm mt-1"
                     value={form.monitoring_end}
                     onChange={(e) => setForm({ ...form, monitoring_end: e.target.value })} />
            </div>
          </div>
          <Button className="rounded-sm" disabled={busy || !form.project_name
                    || !form.client || !form.monitoring_start}
                  onClick={handleCreate}>
            {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Create campaign
          </Button>
        </section>
      )}

      {/* ---------------- 1. standard and parameters ---------------- */}
      {step === 1 && options && (
        <section className="space-y-4">
          <div className="border border-border rounded-sm p-5 space-y-4">
            <div>
              <Label className="text-xs">What is this a report of?</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {(options.media || []).map((m) => (
                  <button key={m.key}
                          onClick={() => setSettings({
                            ...settings, medium: m.key,
                            // A standard from another medium cannot survive
                            // the switch — the server refuses it, and leaving
                            // it selected would look like it had been kept.
                            standard: m.standards.includes(settings.standard)
                              ? settings.standard : "none",
                            analyte_keys: [], profile_id: null,
                          })}
                          className={`text-sm px-4 py-2 rounded-sm border transition-colors ${
                            medium === m.key
                              ? "border-primary bg-primary/10 font-medium"
                              : "border-border text-muted-foreground hover:border-primary/50"}`}>
                    {medium === m.key && <Check className="w-3.5 h-3.5 inline mr-1.5" />}
                    {m.label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                One campaign is one medium and one report. Soil and water
                samples from the same site are two separate campaigns.
              </p>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-xs">Standard</Label>
                <Select value={settings.standard}
                        onValueChange={(v) => setSettings({ ...settings, standard: v })}>
                  <SelectTrigger className="rounded-sm mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {allowedStandards.map((s) => (
                      <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Decision rule</Label>
                <Select value={settings.decision_rule}
                        onValueChange={(v) => setSettings({ ...settings, decision_rule: v })}>
                  <SelectTrigger className="rounded-sm mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {options.decision_rules.map((s) => (
                      <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Stated in the report, as ILAC-G8 requires.
                </p>
              </div>
              <div>
                <Label className="text-xs">Laboratory</Label>
                <Input className="rounded-sm mt-1" value={settings.laboratory}
                       onChange={(e) => setSettings({ ...settings, laboratory: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Accreditation number</Label>
                <Input className="rounded-sm mt-1" value={settings.lab_accreditation}
                       onChange={(e) => setSettings({ ...settings, lab_accreditation: e.target.value })} />
              </div>
            </div>

            <ContextFields
              standard={settings.standard}
              options={options}
              value={settings.default_context}
              onChange={(c) => setSettings({ ...settings, default_context: c })}
            />
          </div>

          <div className="border border-border rounded-sm p-5 space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-sm font-semibold">Parameters</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {settings.analyte_keys.length} selected. This is the client's
                  scope of work, not the standard.
                </p>
              </div>
              <div className="w-64">
                <Select value={settings.profile_id || "__none"}
                        onValueChange={(v) => v !== "__none" && applyProfile(v)}>
                  <SelectTrigger className="rounded-sm">
                    <SelectValue placeholder="Load a saved profile" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">Load a saved profile…</SelectItem>
                    {profiles.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name} ({p.analyte_keys.length})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {grouped.map((g) => (
              <div key={g.key}>
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
                  {g.label}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {g.items.map((a) => {
                    const on = selected.has(a.key);
                    return (
                      <button key={a.key} onClick={() => toggleAnalyte(a.key)}
                              className={`text-xs px-2.5 py-1 rounded-sm border transition-colors ${
                                on ? "border-primary bg-primary/10 text-foreground"
                                   : "border-border text-muted-foreground hover:border-primary/50"}`}>
                        {on && <Check className="w-3 h-3 inline mr-1" />}
                        {a.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <Button className="rounded-sm" disabled={busy}
                    onClick={() => persistSettings(settings)}>
              {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />} Save
            </Button>
            <Button variant="outline" className="rounded-sm"
                    onClick={() => setStep(2)}>Next</Button>
          </div>
        </section>
      )}

      {/* ---------------- 2. samples ---------------- */}
      {step === 2 && options && (
        <section className="space-y-4">
          <div className="border border-border rounded-sm p-5 space-y-3">
            <h2 className="text-sm font-semibold">
              Add a {mediumInfo?.label?.toLowerCase() || "sample"} sample
            </h2>
            <p className="text-xs text-muted-foreground">
              {samples.length} {mediumInfo?.label?.toLowerCase() || ""} sample
              {samples.length === 1 ? "" : "s"} in this campaign.
            </p>
            <div className="grid sm:grid-cols-4 gap-3">
              <div className="sm:col-span-2">
                <Label className="text-xs">Sample code</Label>
                <Input className="rounded-sm mt-1" placeholder="BSA 03-08-2026 S01"
                       value={newSample.code}
                       onChange={(e) => setNewSample({ ...newSample, code: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Column label</Label>
                <Input className="rounded-sm mt-1" placeholder="S01"
                       value={newSample.label}
                       onChange={(e) => setNewSample({ ...newSample, label: e.target.value })} />
              </div>
              <div className="flex items-end">
                <Button className="rounded-sm w-full" disabled={busy} onClick={addSample}>
                  <Plus className="w-4 h-4 mr-2" /> Add
                </Button>
              </div>
            </div>
          </div>

          {samples.length === 0 && (
            <p className="text-sm text-muted-foreground px-1">
              No samples yet. Add them here, or let the results upload create
              them from its column headings.
            </p>
          )}

          {samples.map((s) => (
            <div key={s.id} className="border border-border rounded-sm p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium flex items-center gap-2">
                    {s.label || s.code}
                    <Badge variant="outline" className="rounded-sm text-[10px] uppercase">
                      {s.medium}
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">{s.code}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {s.results?.length || 0} results
                  </p>
                </div>
                <Button variant="ghost" size="sm"
                        className="rounded-sm text-red-400 hover:text-red-300"
                        onClick={() => removeSample(s.id)}>
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
              <ContextFields
                standard={settings.standard}
                options={options}
                value={{ ...BLANK_CONTEXT, ...(s.context || {}) }}
                onChange={(c) => saveSampleContext(s, c)}
              />
            </div>
          ))}

          <div className="flex gap-2">
            <Button variant="outline" className="rounded-sm"
                    onClick={() => setStep(1)}>Back</Button>
            <Button className="rounded-sm" onClick={() => setStep(3)}>Next</Button>
          </div>
        </section>
      )}

      {/* ---------------- 3. results ---------------- */}
      {step === 3 && (
        <section className="space-y-4">
          <div className="border border-border rounded-sm p-5 space-y-3">
            <h2 className="text-sm font-semibold">Upload the results grid</h2>
            <p className="text-xs text-muted-foreground leading-relaxed">
              A CSV with parameters down and sample codes across. The first
              column is the parameter name. Columns headed Unit, Method, LOQ or
              MU% are read as metadata; every other heading is treated as a
              sample code, and any code not already present is created.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <Input type="file" accept=".csv,text/csv"
                     className="rounded-sm max-w-sm"
                     onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <Button className="rounded-sm" disabled={!file || busy} onClick={upload}>
                {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      : <Upload className="w-4 h-4 mr-2" />}
                Upload
              </Button>
            </div>
          </div>

          {ingest && (
            <div className="border border-border rounded-sm p-5 text-sm space-y-2">
              <h3 className="text-sm font-semibold">What was read</h3>
              <p className="text-xs text-muted-foreground">
                {ingest.values_stored} values across{" "}
                {ingest.samples_matched.length + ingest.samples_created.length} samples.
                {ingest.samples_created.length > 0
                  && ` ${ingest.samples_created.length} sample(s) created: ${ingest.samples_created.join(", ")}.`}
                {ingest.values_below_loq > 0
                  && ` ${ingest.values_below_loq} result(s) below the limit of quantification.`}
              </p>
              {ingest.parameters_unresolved.length > 0 && (
                <div className="border border-amber-900/50 bg-amber-950/20 rounded-sm p-3">
                  <p className="text-xs text-amber-300 font-medium">
                    Not matched to a known parameter
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {ingest.parameters_unresolved.join(", ")} — these are kept
                    with their results and printed without a compliance
                    conclusion, not discarded.
                  </p>
                </div>
              )}
              {ingest.values_unparsed.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Kept as text: {ingest.values_unparsed.slice(0, 6).join("; ")}
                </p>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <Button variant="outline" className="rounded-sm"
                    onClick={() => setStep(2)}>Back</Button>
            <Button className="rounded-sm" disabled={busy} onClick={goReview}>
              {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />} Evaluate
            </Button>
          </div>
        </section>
      )}

      {/* ---------------- 4. review ---------------- */}
      {step === 4 && summary && (
        <section className="space-y-4">
          {readiness && !readiness.ready && (
            <div className="border border-amber-900/50 bg-amber-950/20 rounded-sm p-4">
              <p className="text-sm text-amber-300 font-medium flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> Not ready to report
              </p>
              <ul className="mt-2 space-y-1">
                {readiness.blocking.map((b) => (
                  <li key={b} className="text-xs text-muted-foreground">— {b}</li>
                ))}
              </ul>
            </div>
          )}

          {summary.blocking_note && (
            <p className="text-xs text-muted-foreground border border-border rounded-sm p-3">
              {summary.blocking_note}
            </p>
          )}

          <div className="grid sm:grid-cols-4 gap-3">
            {[
              [`${mediumInfo?.label || "Sample"} samples`, summary.samples.length],
              ["Exceedances", summary.total_exceedances],
              ["Standard", summary.standard.replace(/_/g, " ")],
              ["Decision rule", summary.decision_rule.replace(/_/g, " ")],
            ].map(([label, value]) => (
              <div key={label} className="border border-border rounded-sm p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  {label}
                </p>
                <p className="text-lg font-medium mt-0.5">{value}</p>
              </div>
            ))}
          </div>

          <div className="border border-border rounded-sm overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-secondary/50 text-muted-foreground">
                  <th className="text-left px-3 py-2 font-normal">Parameter</th>
                  <th className="text-left px-3 py-2 font-normal">Unit</th>
                  {summary.samples.map((s) => (
                    <th key={s.sample_id} className="text-right px-3 py-2 font-normal">
                      {s.label}
                    </th>
                  ))}
                  <th className="text-right px-3 py-2 font-normal">Limit</th>
                </tr>
              </thead>
              <tbody>
                {summary.rows.map((row, i) => (
                  row.kind === "group" ? (
                    <tr key={`g${i}`} className="bg-secondary/30">
                      <td colSpan={summary.samples.length + 3}
                          className="px-3 py-1.5 font-medium">{row.label}</td>
                    </tr>
                  ) : (
                    <tr key={row.analyte_key} className="border-t border-border">
                      <td className="px-3 py-1.5">{row.analyte_name}</td>
                      <td className="px-3 py-1.5 text-muted-foreground">{row.unit}</td>
                      {row.cells.map((c) => (
                        <td key={c.sample_id}
                            className={`px-3 py-1.5 text-right font-mono ${
                              c.verdict === "exceeds"
                                ? "text-red-400 font-semibold"
                                : c.verdict === "not_assessed"
                                  ? "text-muted-foreground" : ""}`}>
                          {c.display_value}
                        </td>
                      ))}
                      <td className="px-3 py-1.5 text-right text-muted-foreground font-mono">
                        {row.limit_display}
                      </td>
                    </tr>
                  )
                ))}
              </tbody>
            </table>
          </div>

          {comparison?.applicable && (
            <div className="border border-border rounded-sm p-4">
              <h3 className="text-sm font-semibold">
                What the limits would have been under a different land use
              </h3>
              <p className="text-xs text-muted-foreground mt-1 mb-3">
                Applied: {comparison.applied_land_use || "not stated"}.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground">
                      <th className="text-left px-2 py-1 font-normal">Parameter</th>
                      {comparison.land_uses.map((l) => (
                        <th key={l.key} className="text-right px-2 py-1 font-normal">
                          {l.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.rows.map((r) => (
                      <tr key={r.analyte_key} className="border-t border-border">
                        <td className="px-2 py-1">{r.analyte_name}</td>
                        {comparison.land_uses.map((l) => (
                          <td key={l.key}
                              className={`px-2 py-1 text-right font-mono ${
                                l.key === comparison.applied_land_use
                                  ? "font-semibold" : "text-muted-foreground"}`}>
                            {r.values[l.key] === null || r.values[l.key] === undefined
                              ? "—" : r.values[l.key]}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <Button variant="outline" className="rounded-sm"
                    onClick={() => setStep(3)}>Back</Button>
            <Button variant="outline" className="rounded-sm"
                    onClick={() => nav(`/campaigns/${campaignId}`)}>
              Open campaign
            </Button>
          </div>
        </section>
      )}

      {search.get("type") && step === 0 && (
        <p className="text-xs text-muted-foreground px-1">
          Report generation for this campaign type is not built yet. Everything
          up to the evaluated matrix is.
        </p>
      )}
    </div>
  );
}
