import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Save } from "lucide-react";

import { createCampaign, getCampaign, updateCampaign } from "@/lib/api";
import { CAMPAIGN_FORM } from "@/constants/testIds";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

// Gases whose units are declared per column. PM10 and PM2.5 are measured
// gravimetrically and are always µg/m³, so they are not listed.
const GAS_UNIT_FIELDS = [
  { key: "SO2", label: "SO\u2082" },
  { key: "NO", label: "NO" },
  { key: "NO2", label: "NO\u2082" },
  { key: "NOx", label: "NOx" },
  { key: "O3", label: "O\u2083" },
  { key: "H2S", label: "H\u2082S" },
  { key: "CO", label: "CO" },
];

// What the BSA fleet's analysers actually export: six gases in ppb, CO in ppm.
const DEFAULT_GAS_UNITS_MAP = {
  SO2: "ppb", NO: "ppb", NO2: "ppb", NOx: "ppb",
  O3: "ppb", H2S: "ppb", CO: "ppm",
};

const NOISE_CATEGORIES = [
  { value: "A", label: "A — Low-density residential, parks, hospitals, schools" },
  { value: "B", label: "B — Medium-density residential" },
  { value: "C", label: "C — High-density residential and mixed commercial" },
  { value: "D", label: "D — Commercial, warehouses, financial centres" },
  { value: "roadside", label: "Roadside — main roads and highways" },
  { value: "industrial", label: "Industrial zones" },
  { value: "construction", label: "Construction work site" },
  { value: "tbd", label: "To be determined by the consultant" },
];

// A construction site has no standard of its own. Article (7) gives it the
// standard of the zone around it plus a correction, so the zone has to be
// named separately — construction cannot be its own base.
const CONSTRUCTION_BASE_CATEGORIES = NOISE_CATEGORIES.filter(
  (c) => c.value !== "construction" && c.value !== "tbd");

// Table (4) — the correction depends on how long activities run each day.
const CONSTRUCTION_BANDS = [
  { value: 2, label: "Up to 2.5 hours (+10 dB)" },
  { value: 6, label: "From 2.5 to 8 hours (+5 dB)" },
  { value: 10, label: "Over 8 hours (no correction)" },
];


// The monitoring window decides the report's duration, its data capture and
// therefore its conclusion, and it is the field most easily got wrong: the
// picker shows the month first, so 06/07 typed as "6 July" is stored as
// 7 June. That slip has produced 720-hour reports at 3% capture more than
// once. Echoing the dates in words was not enough — a warning that can be
// scrolled past is a warning that gets scrolled past — so an impossible
// window now stops the save and an unusual one has to be read first.
function checkWindow(startStr, endStr) {
  const a = startStr ? new Date(startStr) : null;
  const b = endStr ? new Date(endStr) : null;
  if (!a || !b || Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) {
    return { level: "none", hours: null };
  }
  const hours = (b - a) / 3600000;
  if (hours <= 0) {
    return {
      level: "stop", hours,
      message: "The window ends before it starts.",
      fix: "Check which box holds which date — the picker shows the month first.",
    };
  }
  // Confirmed rather than forbidden. The month-first slip lands on exactly
  // 30.0 days, so a "longer than 30 days" rule misses the one case it was
  // written for; and campaigns genuinely do run for weeks, so a hard limit
  // would eventually block real work. Above a fortnight the length has to be
  // acknowledged deliberately, which a mistyped month never is.
  if (hours > 24 * 14) {
    return {
      level: "confirm", hours,
      message: `This window is ${(hours / 24).toFixed(0)} days long.`,
      fix: "A month entered in place of a day reads exactly like this. If the "
         + "campaign really did run this long, confirm it below.",
    };
  }
  if (hours > 48) {
    return {
      level: "warn", hours,
      message: `This window covers ${(hours / 24).toFixed(1)} days, not the `
             + "usual 24 hours.",
      fix: "Data capture is measured against the whole window, so a short "
         + "record inside a long window reports as low capture.",
    };
  }
  return {
    level: "ok", hours,
    message: `A ${hours.toFixed(0)}-hour window, as expected for an attended survey.`,
  };
}

const defaults = {
  campaign_type: "air",
  noise_category: "tbd",
  day_start_hour: 7,
  day_end_hour: 20,
  construction_base_category: "",
  construction_hours_per_day: "",
  meter_model: "",
  meter_serial: "",
  calibrator_model: "",
  calibration_level_db: 94,
  mic_height_m: 1.5,
  met_temp_max_c: "", met_temp_min_c: "",
  met_rh_max_pct: "", met_rh_min_pct: "",
  met_wind_max_ms: "", met_wind_min_ms: "", met_wind_mean_ms: "",
  met_wind_prevailing: "",
  site_conditions_note: "",
  project_name: "",
  client: "",
  provider: "Bander Said Allehiany (BSA)",
  site_name: "",
  latitude: "",
  longitude: "",
  inlet_height_m: 5.0,
  gas_units: "ugm3",
  gas_units_map: { ...DEFAULT_GAS_UNITS_MAP },
  facility_latitude: "",
  facility_longitude: "",
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

/**
 * Units for a campaign loaded from the server.
 *
 * A campaign saved before per-gas units existed carries only the single
 * `gas_units` value. Spreading that value across all seven gases reproduces
 * its current behaviour exactly, so opening an old campaign never changes
 * the numbers it would produce — it only makes the setting visible and
 * editable.
 */
function unitsMapFrom(campaign) {
  const stored = campaign?.gas_units_map;
  if (stored && Object.keys(stored).length > 0) {
    return { ...DEFAULT_GAS_UNITS_MAP, ...stored };
  }
  const legacy = campaign?.gas_units || "ugm3";
  return Object.fromEntries(GAS_UNIT_FIELDS.map((g) => [g.key, legacy]));
}

/**
 * Fold Arabic script into the ASCII the parser expects.
 *
 * A camera set to Arabic stamps the position as \u0662\u0664\u066B\u0665\u0665\u0663\u0664 \u0634\u0645\u0627\u0644 rather than
 * 24.5534N — different digits, a different decimal mark, and the compass
 * point written as a word. Normalising here means one parser handles a
 * photograph taken on an Arabic handset and an English one alike.
 */
function normaliseArabic(text) {
  let out = "";
  for (const ch of text) {
    const c = ch.codePointAt(0);
    if (c >= 0x0660 && c <= 0x0669) {        // Arabic-Indic digits
      out += String(c - 0x0660);
    } else if (c >= 0x06f0 && c <= 0x06f9) { // Extended Arabic-Indic digits
      out += String(c - 0x06f0);
    } else if (c === 0x066b) {               // Arabic decimal separator
      out += ".";
    } else if (c === 0x066c) {               // Arabic thousands separator
      // dropped
    } else if (c === 0x060c) {               // Arabic comma
      out += ",";
    } else if (c === 0x200e || c === 0x200f || c === 0x061c) {
      // bidi marks carry no meaning here
    } else {
      out += ch;
    }
  }
  // compass points written as words; longest first so no prefix is clipped
  return out
    .replace(/\u0634\u0645\u0627\u0644\u064a|\u0634\u0645\u0627\u0644/g, "N")   // shamal - north
    .replace(/\u062c\u0646\u0648\u0628\u064a|\u062c\u0646\u0648\u0628/g, "S")   // janub - south
    .replace(/\u0634\u0631\u0642\u064a|\u0634\u0631\u0642/g, "E")                 // sharq - east
    .replace(/\u063a\u0631\u0628\u064a|\u063a\u0631\u0628/g, "W");                // gharb - west
}

/**
 * Read a full coordinate pair out of one string.
 *
 * Field photographs carry the position stamped across the image as a single
 * line — "24.5534N 39.6027E". Split across two inputs that has to be read,
 * divided and typed twice, which is where a leading digit goes missing. Read
 * as one string it is entered the way it is written.
 *
 * Accepts the forms that actually turn up:
 *   24.5534N 39.6027E      24.5534, 39.6027
 *   24.5534 N, 39.6027 E   N 24.5534 E 39.6027
 *   24.5534°N 39.6027°E
 * Arabic digits and compass words are folded first, so a photograph taken
 * on an Arabic handset reads the same as an English one.
 * Hemisphere letters, where present, decide which number is which, so a pair
 * written longitude-first is still read correctly.
 */
export function parseCoordinates(text) {
  if (!text || !text.trim()) return null;
  const cleaned = normaliseArabic(text)
    .replace(/[°º]/g, " ")
    .replace(/\u2212/g, "-");

  // a number with an optional hemisphere letter on either side of it
  const re = /([NSEWnsew])?\s*(-?\d{1,3}(?:\.\d+)?)\s*([NSEWnsew])?/g;
  const found = [];
  let m;
  while ((m = re.exec(cleaned)) !== null && found.length < 2) {
    if (m[2] === undefined) continue;
    found.push({
      value: parseFloat(m[2]),
      hemi: (m[1] || m[3] || "").toUpperCase(),
    });
  }
  if (found.length < 2) return null;

  const [first, second] = found;
  // if either letter identifies a longitude first, the pair is reversed
  const reversed =
    first.hemi === "E" || first.hemi === "W" ||
    second.hemi === "N" || second.hemi === "S";
  const latPart = reversed ? second : first;
  const lonPart = reversed ? first : second;

  const applySign = (part, negativeLetter) => {
    if (!part.hemi) return part.value;
    const abs = Math.abs(part.value);
    return part.hemi === negativeLetter ? -abs : abs;
  };

  const lat = applySign(latPart, "S");
  const lon = applySign(lonPart, "W");

  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
}

export default function CampaignForm({ mode }) {
  const { id } = useParams();
  const nav = useNavigate();
  const [params] = useSearchParams();
  // The type comes from the chooser card and never changes afterwards —
  // an air campaign cannot become a noise one, because its readings,
  // engine and report are different things.
  const urlType = params.get("type") === "noise" ? "noise" : "air";
  const [form, setForm] = useState({ ...defaults, campaign_type: urlType });
  const [loading, setLoading] = useState(mode === "edit");
  const [saving, setSaving] = useState(false);
  // Cleared whenever the window changes, so a confirmation cannot be
  // inherited by a different set of dates.
  const [longWindowOk, setLongWindowOk] = useState(false);
  const [pasted, setPasted] = useState("");
  const [pastedError, setPastedError] = useState(false);

  useEffect(() => {
    if (mode !== "edit" || !id) return;
    (async () => {
      try {
        const c = await getCampaign(id);
        setForm({
          campaign_type: c.campaign_type || "air",
          noise_category: c.noise_category || "tbd",
          day_start_hour: c.day_start_hour ?? 7,
          day_end_hour: c.day_end_hour ?? 20,
          construction_base_category: c.construction_base_category || "",
          construction_hours_per_day: c.construction_hours_per_day ?? "",
          meter_model: c.meter_model || "",
          meter_serial: c.meter_serial || "",
          calibrator_model: c.calibrator_model || "",
          calibration_level_db: c.calibration_level_db ?? 94,
          mic_height_m: c.mic_height_m ?? 1.5,
          met_temp_max_c: c.met_temp_max_c ?? "",
          met_temp_min_c: c.met_temp_min_c ?? "",
          met_rh_max_pct: c.met_rh_max_pct ?? "",
          met_rh_min_pct: c.met_rh_min_pct ?? "",
          met_wind_max_ms: c.met_wind_max_ms ?? "",
          met_wind_min_ms: c.met_wind_min_ms ?? "",
          met_wind_mean_ms: c.met_wind_mean_ms ?? "",
          met_wind_prevailing: c.met_wind_prevailing || "",
          site_conditions_note: c.site_conditions_note || "",
          project_name: c.project_name || "",
          client: c.client || "",
          provider: c.provider || "",
          site_name: c.site_name || "",
          latitude: c.latitude ?? "",
          facility_latitude: c.facility_latitude ?? "",
          facility_longitude: c.facility_longitude ?? "",
          longitude: c.longitude ?? "",
          inlet_height_m: c.inlet_height_m ?? 5.0,
          gas_units: c.gas_units || "ugm3",
          gas_units_map: unitsMapFrom(c),
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

  const setGasUnit = (gas) => (value) =>
    setForm((f) => ({ ...f, gas_units_map: { ...f.gas_units_map, [gas]: value } }));

  const resetGasUnits = () =>
    setForm((f) => ({ ...f, gas_units_map: { ...DEFAULT_GAS_UNITS_MAP } }));

  const applyPasted = (value) => {
    setPasted(value);
    if (!value.trim()) {
      setPastedError(false);
      return;
    }
    const parsed = parseCoordinates(value);
    if (!parsed) {
      setPastedError(true);
      return;
    }
    setPastedError(false);
    setForm((f) => ({
      ...f,
      latitude: String(parsed.lat),
      longitude: String(parsed.lon),
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    // Checked here as well as on the button: the form can still be submitted
    // by pressing Enter in any field, which bypasses a disabled button.
    const win = checkWindow(form.monitoring_start, form.monitoring_end);
    if (win.level === "stop") {
      toast.error(win.message);
      return;
    }
    if (win.level === "confirm" && !longWindowOk) {
      toast.error("Confirm the monitoring window length before saving.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        day_start_hour: parseInt(form.day_start_hour, 10) || 7,
        day_end_hour: parseInt(form.day_end_hour, 10) || 20,
        construction_base_category:
          form.construction_base_category || null,
        construction_hours_per_day:
          form.construction_hours_per_day === ""
            ? null
            : parseFloat(form.construction_hours_per_day),
        // Blank weather fields must arrive as null: an empty string is not
        // a number, and the report omits the table when nothing was
        // recorded rather than printing empty rows.
        ...Object.fromEntries(
          ["calibration_level_db", "mic_height_m", "met_temp_max_c",
           "met_temp_min_c", "met_rh_max_pct", "met_rh_min_pct",
           "met_wind_max_ms", "met_wind_min_ms", "met_wind_mean_ms"]
            .map((k) => [k, form[k] === "" || form[k] === null
              ? null : Number(form[k])])),
        latitude: parseFloat(form.latitude),
        facility_latitude: form.facility_latitude === "" || form.facility_latitude == null
          ? null : parseFloat(form.facility_latitude),
        facility_longitude: form.facility_longitude === "" || form.facility_longitude == null
          ? null : parseFloat(form.facility_longitude),
        longitude: parseFloat(form.longitude),
        inlet_height_m: parseFloat(form.inlet_height_m),
        gas_units_map: form.gas_units_map || {},
        // Naive local time — the analyser logs local Saudi time and the
        // report is read in local time. Converting to UTC here shifted the
        // window 3 h against the readings and cost 3 h of data capture.
        monitoring_start: form.monitoring_start,
        monitoring_end: form.monitoring_end,
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

  const windowCheck = checkWindow(form.monitoring_start, form.monitoring_end);
  const windowBlocked = windowCheck.level === "stop"
    || (windowCheck.level === "confirm" && !longWindowOk);
  const unitsMap = form.gas_units_map || {};
  const allUgm3 = GAS_UNIT_FIELDS.every((g) => (unitsMap[g.key] || "ugm3") === "ugm3");

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

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">
            Coordinates from the field photo
          </Label>
          <Input
            value={pasted}
            onChange={(e) => applyPasted(e.target.value)}
            placeholder="24.5534N 39.6027E"
            className="rounded-sm font-mono"
          />
          {pastedError ? (
            <p className="text-[11px] text-amber-500">
              Could not read a coordinate pair from that. Enter latitude and
              longitude below instead.
            </p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Type the position exactly as it appears on the photograph and both
              fields below are filled for you. Check the values it reads back.
            </p>
          )}
        </div>

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

        <div className="space-y-1.5">
          <Label className="text-xs">Facility latitude (optional)</Label>
          <Input className="rounded-sm h-9" value={form.facility_latitude || ""}
                 onChange={(e) => setForm((f) => ({ ...f, facility_latitude: e.target.value }))}
                 placeholder="22.7185" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Facility longitude (optional)</Label>
          <Input className="rounded-sm h-9" value={form.facility_longitude || ""}
                 onChange={(e) => setForm((f) => ({ ...f, facility_longitude: e.target.value }))}
                 placeholder="42.6835" />
          <p className="text-[11px] text-muted-foreground">
            Coordinates of the plant or source. If given, the report states the
            station's distance and bearing from it, alongside the prevailing
            wind — as measurements only, with no upwind/downwind conclusion.
          </p>
        </div>
      </Section>

      {form.campaign_type === "noise" && (
      <Section title="Noise settings">
        <p className="text-[11px] text-muted-foreground -mt-1">
          The land-use category decides which NCEC limits the report judges
          against. Choosing "to be determined" produces a report that states
          the measured levels against every category and leaves the
          assessment to the consultant. The day period is 07:00–20:00 under
          Article (1) of the Executive Regulation for Noise; change it only
          where a different window has been agreed in writing.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>NCEC land-use category</Label>
            <select
              value={form.noise_category}
              onChange={(e) =>
                setForm((f) => ({ ...f, noise_category: e.target.value }))}
              className="w-full h-9 rounded-sm border border-border bg-background px-2 text-sm"
              data-testid="noise-category"
            >
              {NOISE_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Day period starts</Label>
              <Input type="number" min={0} max={23}
                     value={form.day_start_hour}
                     onChange={(e) => setForm((f) => ({ ...f, day_start_hour: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Day period ends</Label>
              <Input type="number" min={0} max={23}
                     value={form.day_end_hour}
                     onChange={(e) => setForm((f) => ({ ...f, day_end_hour: e.target.value }))} />
            </div>
          </div>
          {form.noise_category === "construction" && (
            <div className="md:col-span-2 space-y-3 rounded-sm border border-border bg-muted/30 p-3">
              <p className="text-[11px] text-muted-foreground">
                A construction work site has no standard of its own.
                Article (7) allows it to exceed the standard of the zone
                around it, by the Table (4) correction, and only between
                07:00 and 18:00. Both the surrounding zone and the duration
                of activities are needed. Left blank, the report states the
                measured levels and makes no compliance judgement.
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Surrounding zone</Label>
                  <select
                    value={form.construction_base_category}
                    onChange={(e) => setForm((f) => ({
                      ...f, construction_base_category: e.target.value }))}
                    className="w-full h-9 rounded-sm border border-border bg-background px-2 text-sm"
                    data-testid="construction-base-category"
                  >
                    <option value="">Not stated — no verdict</option>
                    {CONSTRUCTION_BASE_CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label>Duration of activities</Label>
                  <select
                    value={form.construction_hours_per_day}
                    onChange={(e) => setForm((f) => ({
                      ...f, construction_hours_per_day: e.target.value }))}
                    className="w-full h-9 rounded-sm border border-border bg-background px-2 text-sm"
                    data-testid="construction-hours"
                  >
                    <option value="">Not stated — no verdict</option>
                    {CONSTRUCTION_BANDS.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}
          <div className="space-y-1.5">
            <Label>Sound level meter</Label>
            <Input value={form.meter_model}
                   onChange={(e) => setForm((f) => ({ ...f, meter_model: e.target.value }))}
                   placeholder="Cirrus Noise Meter Type 1" />
          </div>
          <div className="space-y-1.5">
            <Label>Meter serial number</Label>
            <Input value={form.meter_serial}
                   onChange={(e) => setForm((f) => ({ ...f, meter_serial: e.target.value }))}
                   placeholder="G330052" />
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          L Day and L Night are energy averages over the day period and its
          complement. The regulation's default of 07:00–19:00 is preset.
        </p>

        <div className="grid gap-3 md:grid-cols-3 pt-1">
          <div className="space-y-1.5">
            <Label>Acoustic calibrator</Label>
            <Input value={form.calibrator_model}
                   onChange={(e) => setForm((f) => ({ ...f, calibrator_model: e.target.value }))}
                   placeholder="Cirrus acoustic calibrator" />
          </div>
          <div className="space-y-1.5">
            <Label>Field check level (dB)</Label>
            <Input type="number" step="0.1" value={form.calibration_level_db}
                   onChange={(e) => setForm((f) => ({ ...f, calibration_level_db: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Microphone height (m)</Label>
            <Input type="number" step="0.1" value={form.mic_height_m}
                   onChange={(e) => setForm((f) => ({ ...f, mic_height_m: e.target.value }))} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Site conditions noted during the survey</Label>
          <Input value={form.site_conditions_note}
                 onChange={(e) => setForm((f) => ({ ...f, site_conditions_note: e.target.value }))}
                 placeholder="Optional — sources present, activities, interruptions" />
        </div>
      </Section>
      )}

      {form.campaign_type === "noise" && (
      <Section title="Meteorological conditions">
        <p className="text-[11px] text-muted-foreground -mt-1">
          A sound level meter carries no weather sensors, so these are
          entered from the site record. Wind and temperature affect sound
          propagation and the regulator's format carries them as a table.
          Leave blank and the table is omitted from the report.
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          {[["met_temp_max_c", "Temperature max (°C)"],
            ["met_temp_min_c", "Temperature min (°C)"],
            ["met_rh_max_pct", "Humidity max (%)"],
            ["met_rh_min_pct", "Humidity min (%)"],
            ["met_wind_max_ms", "Wind speed max (m/s)"],
            ["met_wind_min_ms", "Wind speed min (m/s)"],
            ["met_wind_mean_ms", "Mean wind speed (m/s)"]].map(([k, lab]) => (
            <div className="space-y-1.5" key={k}>
              <Label>{lab}</Label>
              <Input type="number" step="0.1" value={form[k]}
                     onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} />
            </div>
          ))}
          <div className="space-y-1.5">
            <Label>Prevailing wind direction</Label>
            <Input value={form.met_wind_prevailing}
                   onChange={(e) => setForm((f) => ({ ...f, met_wind_prevailing: e.target.value }))}
                   placeholder="E" />
          </div>
        </div>
      </Section>
      )}

      {form.campaign_type !== "noise" && (
      <Section title="Gas units">
        <p className="text-[11px] text-muted-foreground -mt-1">
          The units of each gas column in the file you will upload. NCEC limits
          are µg/m³ at 25 °C and 101.3 kPa, so ppb and ppm columns are converted
          on ingest. Analyser exports are commonly mixed — CO in ppm while the
          other gases are in ppb — which is why each gas is set separately.
        </p>

        <div
          data-testid="campaign-gas-units-map"
          className="grid grid-cols-2 md:grid-cols-4 gap-3"
        >
          {GAS_UNIT_FIELDS.map((gas) => (
            <div key={gas.key} className="space-y-1">
              <Label className="text-xs text-muted-foreground">{gas.label}</Label>
              <Select
                value={unitsMap[gas.key] || "ppb"}
                onValueChange={setGasUnit(gas.key)}
              >
                <SelectTrigger
                  data-testid={`campaign-gas-units-${gas.key}`}
                  className="rounded-sm h-9"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ppb">ppb</SelectItem>
                  <SelectItem value="ppm">ppm</SelectItem>
                  <SelectItem value="ugm3">µg/m³</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ))}
        </div>

        {allUgm3 && (
          <p className="text-[11px] text-amber-500">
            Every gas is set to µg/m³, so no conversion will be applied and the
            file's numbers will be reported exactly as they appear. Confirm your
            analyser really does export µg/m³ — most export ppb, and CO in ppm.
          </p>
        )}

        <div className="flex items-center justify-between pt-1">
          <p className="text-[11px] text-muted-foreground">
            A units row inside the uploaded file overrides these, column by
            column. PM10 and PM2.5 are always µg/m³ and are not listed.
          </p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={resetGasUnits}
            className="rounded-sm text-[11px] h-7"
          >
            Reset to ppb / CO ppm
          </Button>
        </div>
      </Section>

      )}

      <Section title="Monitoring window">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Start" required>
            <Input
              data-testid={CAMPAIGN_FORM.monitoringStart}
              type="datetime-local"
              value={form.monitoring_start}
              onChange={(e) => { setLongWindowOk(false); set("monitoring_start")(e); }}
              required
              className="rounded-sm font-mono"
            />
          </Field>
          <Field label="End" required>
            <Input
              data-testid={CAMPAIGN_FORM.monitoringEnd}
              type="datetime-local"
              value={form.monitoring_end}
              onChange={(e) => { setLongWindowOk(false); set("monitoring_end")(e); }}
              required
              className="rounded-sm font-mono"
            />
          </Field>
        </div>

        {/* Reads the window back in words, then says whether it is usable.
            The wording is deliberately specific about what to do next: an
            error that only reports a problem leaves the person guessing at
            which of the two boxes is wrong. */}
        {(form.monitoring_start || form.monitoring_end) && (() => {
          const fmt = (v) => {
            if (!v) return "—";
            const d = new Date(v);
            return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(
              "en-GB", { day: "numeric", month: "long", year: "numeric",
                         hour: "2-digit", minute: "2-digit" });
          };
          const win = checkWindow(form.monitoring_start, form.monitoring_end);
          const tone = {
            stop: "border-rose-200 bg-rose-50 text-rose-800",
            confirm: "border-rose-200 bg-rose-50 text-rose-800",
            warn: "border-amber-200 bg-amber-50 text-amber-800",
            ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
          }[win.level];
          return (
            <>
              <p className="text-[11px] text-muted-foreground">
                Reads as <span className="text-foreground">{fmt(form.monitoring_start)}</span>
                {" → "}<span className="text-foreground">{fmt(form.monitoring_end)}</span>
                {win.hours > 0 && (
                  <>{"  ·  "}{win.hours < 48 ? `${win.hours.toFixed(1)} hours`
                    : `${(win.hours / 24).toFixed(1)} days`}</>
                )}
              </p>
              {tone && (
                <div
                  data-testid="monitoring-window-check"
                  className={`mt-2 rounded-sm border px-3 py-2 text-[12px] leading-snug ${tone}`}
                >
                  <span className="font-medium">
                    {win.level === "stop" || win.level === "confirm"
                      ? "Stop" : win.level === "warn" ? "Check" : "OK"}
                  </span>
                  {" — "}{win.message}
                  {win.fix && (
                    <span className="mt-1 block opacity-80">{win.fix}</span>
                  )}
                  {win.level === "confirm" && (
                    <label className="mt-2 flex items-center gap-2 font-medium">
                      <input
                        type="checkbox"
                        data-testid="monitoring-window-confirm"
                        checked={longWindowOk}
                        onChange={(e) => setLongWindowOk(e.target.checked)}
                      />
                      Yes, this campaign ran for {(win.hours / 24).toFixed(0)} days
                    </label>
                  )}
                </div>
              )}
            </>
          );
        })()}
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
          {/* Assigned by the server when the first report is generated, so a
              campaign that never produces one never consumes a number and the
              date inside the number is the issue date. A number already on the
              campaign stays editable — an old job entered late still needs its
              own number typed in. */}
          <Field label="Report number">
            {form.report_number ? (
              <Input
                data-testid={CAMPAIGN_FORM.reportNumber}
                value={form.report_number}
                onChange={set("report_number")}
                className="rounded-sm font-mono"
              />
            ) : (
              <div
                data-testid={CAMPAIGN_FORM.reportNumber}
                className="flex h-9 items-center rounded-sm border border-input
                           bg-muted px-3 text-sm text-muted-foreground"
              >
                Assigned when the first report is generated
              </div>
            )}
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
          disabled={saving || windowBlocked}
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
      <header className="px-4 py-2 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground bg-secondary/40">
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
