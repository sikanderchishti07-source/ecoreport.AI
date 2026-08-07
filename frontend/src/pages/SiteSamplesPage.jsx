/**
 * Site Samples — water and soil collected during a visit.
 *
 * They have a page of their own rather than a corner of the campaign page
 * because they are a job in their own right: taken on site, carried to a
 * laboratory, and answered for weeks later. On a campaign page they would be a
 * footnote nobody opens.
 *
 * Nothing here reads results, because there is no water or soil reporting
 * engine yet. It records what only the visit can produce — when, where, by
 * whom, and a photograph — and stops. When the engines are built this is where
 * results will be entered, which is most likely where the page was always
 * going.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Droplets, Image as ImageIcon, Loader2, MapPin, Mountain, Plus, Search,
  Trash2, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createSiteSample, deleteSiteSample, listSiteSamples, siteSamplePhotoUrl,
} from "@/lib/api";
import AuthImage from "@/components/AuthImage";

const KINDS = [
  { key: "water", label: "Water", Icon: Droplets, tone: "text-sky-600" },
  { key: "soil", label: "Soil", Icon: Mountain, tone: "text-amber-700" },
];

function fmt(dt) {
  if (!dt) return "—";
  const d = new Date(dt);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function SiteSamplesPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [adding, setAdding] = useState(false);
  const [photo, setPhoto] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    kind: "water", project_name: "", client: "", site_name: "",
    latitude: "", longitude: "", taken_at: "", recorded_by: "", note: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listSiteSamples({ q: q || undefined, kind: kind || undefined }));
    } catch {
      toast.error("Could not load the samples");
    } finally {
      setLoading(false);
    }
  }, [q, kind]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);   // let typing settle
    return () => clearTimeout(t);
  }, [load, q]);

  const totals = useMemo(() => ({
    water: rows.filter((r) => r.kind === "water").length,
    soil: rows.filter((r) => r.kind === "soil").length,
    visits: new Set(rows.map((r) => r.visit_id)).size,
  }), [rows]);

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e?.target ? e.target.value : e }));

  const save = async () => {
    if (!form.site_name.trim() && !form.project_name.trim()) {
      toast.error("A project or a site is needed");
      return;
    }
    setSaving(true);
    try {
      await createSiteSample({
        // Added by hand, so it is its own visit rather than being folded into
        // one the operator recorded — a sample entered in the office days
        // later did not come from that visit and should not claim to.
        visit_id: `office-${Date.now()}`,
        ...form,
        latitude: form.latitude || undefined,
        longitude: form.longitude || undefined,
        taken_at: form.taken_at || undefined,
      }, photo);
      toast.success("Sample recorded");
      setAdding(false);
      setPhoto(null);
      setForm((f) => ({ ...f, latitude: "", longitude: "", note: "" }));
      load();
    } catch {
      toast.error("Could not save the sample");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row) => {
    if (!window.confirm(
      `Delete ${row.kind} sample ${row.number} from ${row.site_name || "this site"}?`
      + "\n\nThe photograph goes with it. This cannot be undone.")) return;
    try {
      await deleteSiteSample(row.id);
      toast.success("Sample deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.status === 403
        ? "Only an admin can delete a sample"
        : "Could not delete it");
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Site Samples</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Water and soil collected on site. Held for the reporting engines,
            which do not exist yet.
          </p>
        </div>
        <Button className="rounded-sm ml-auto" onClick={() => setAdding((a) => !a)}>
          {adding ? <X className="w-4 h-4 mr-2" /> : <Plus className="w-4 h-4 mr-2" />}
          {adding ? "Cancel" : "Add a sample"}
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3 max-w-md">
        {[["Water", totals.water], ["Soil", totals.soil], ["Visits", totals.visits]]
          .map(([k, n]) => (
            <div key={k} className="rounded-sm border border-border px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{k}</div>
              <div className="text-xl font-semibold tabular-nums">{n}</div>
            </div>
          ))}
      </div>

      {adding && (
        <div className="rounded-sm border border-border p-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-4">
            <div>
              <Label className="text-xs">Type</Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {KINDS.map(({ key, label }) => (
                  <button key={key} type="button"
                    onClick={() => setForm((f) => ({ ...f, kind: key }))}
                    className={`rounded-sm border px-2 py-2 text-xs
                      ${form.kind === key
                        ? "border-primary bg-primary/5 font-medium"
                        : "border-border"}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div><Label className="text-xs">Project</Label>
              <Input className="rounded-sm mt-1" value={form.project_name}
                onChange={set("project_name")} /></div>
            <div><Label className="text-xs">Client</Label>
              <Input className="rounded-sm mt-1" value={form.client}
                onChange={set("client")} /></div>
            <div><Label className="text-xs">Site</Label>
              <Input className="rounded-sm mt-1" value={form.site_name}
                onChange={set("site_name")} /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div><Label className="text-xs">Latitude</Label>
              <Input className="rounded-sm mt-1 font-mono" value={form.latitude}
                onChange={set("latitude")} placeholder="24.621855" /></div>
            <div><Label className="text-xs">Longitude</Label>
              <Input className="rounded-sm mt-1 font-mono" value={form.longitude}
                onChange={set("longitude")} placeholder="46.235300" /></div>
            <div><Label className="text-xs">Taken at</Label>
              <Input type="datetime-local" className="rounded-sm mt-1 font-mono"
                value={form.taken_at} onChange={set("taken_at")} /></div>
            <div><Label className="text-xs">Collected by</Label>
              <Input className="rounded-sm mt-1" value={form.recorded_by}
                onChange={set("recorded_by")} placeholder="Operator name" /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><Label className="text-xs">Note</Label>
              <Input className="rounded-sm mt-1" value={form.note}
                onChange={set("note")} /></div>
            <div><Label className="text-xs">Photograph</Label>
              <Input type="file" accept="image/*" className="rounded-sm mt-1"
                onChange={(e) => setPhoto(e.target.files?.[0] || null)} /></div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            A sample added here is recorded as its own visit — it did not come
            from one the operator logged, and should not claim to.
          </p>
          <Button className="rounded-sm" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            Save sample
          </Button>
        </div>
      )}

      <div className="flex gap-2 flex-wrap items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground" />
          <Input className="rounded-sm pl-8" placeholder="Project, client, site or person…"
            value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex gap-1.5">
          {[["", "All"], ["water", "Water"], ["soil", "Soil"]].map(([k, label]) => (
            <button key={label} type="button" onClick={() => setKind(k)}
              className={`rounded-full border px-3 py-1.5 text-xs
                ${kind === k ? "border-foreground font-medium" : "border-border text-muted-foreground"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-sm border border-dashed border-border py-12 text-center">
          <p className="text-sm text-muted-foreground">No samples recorded yet.</p>
          <p className="text-xs text-muted-foreground mt-1">
            They arrive from the field app, or can be added here.
          </p>
        </div>
      ) : (
        <div className="rounded-sm border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[10px] uppercase tracking-wider
                             text-muted-foreground">
                <th className="text-left font-medium px-3 py-2">Sample</th>
                <th className="text-left font-medium px-3 py-2">Project · site</th>
                <th className="text-left font-medium px-3 py-2">Taken</th>
                <th className="text-left font-medium px-3 py-2">Position</th>
                <th className="text-left font-medium px-3 py-2">By</th>
                <th className="text-left font-medium px-3 py-2">Photo</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const K = KINDS.find((k) => k.key === r.kind) || KINDS[0];
                return (
                  <tr key={r.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2.5">
                      <span className="inline-flex items-center gap-2 font-medium">
                        <K.Icon className={`w-4 h-4 ${K.tone}`} />
                        {K.label} {r.number}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <div>{r.project_name || "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {[r.client, r.site_name].filter(Boolean).join(" · ") || "—"}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-xs font-mono">{fmt(r.taken_at)}</td>
                    <td className="px-3 py-2.5 text-xs font-mono">
                      {r.latitude != null && r.longitude != null ? (
                        <span className="inline-flex items-center gap-1.5">
                          <MapPin className="w-3 h-3 text-muted-foreground" />
                          {Number(r.latitude).toFixed(6)}, {Number(r.longitude).toFixed(6)}
                          {r.accuracy_m != null && (
                            <span className="text-muted-foreground">
                              ±{Math.round(r.accuracy_m)} m
                            </span>
                          )}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-xs">{r.recorded_by || "—"}</td>
                    <td className="px-3 py-2.5">
                      {r.photo_path ? (
                        <AuthImage
                          src={siteSamplePhotoUrl(r.id)}
                          alt={`${r.kind} ${r.number}`}
                          className="h-10 w-10 rounded-sm object-cover border border-border"
                        />
                      ) : (
                        <ImageIcon className="w-4 h-4 text-muted-foreground/40" />
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button type="button" onClick={() => remove(r)}
                        className="text-muted-foreground hover:text-destructive"
                        aria-label="Delete sample">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Laboratory results, chain of custody and sample identifiers are not
        recorded here. Those belong with the water and soil reporting engines,
        designed against their own requirements — half-built, such a record
        looks official without being so.
      </p>
    </div>
  );
}
