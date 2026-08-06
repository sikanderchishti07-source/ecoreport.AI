import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Save, Trash2, Truck } from "lucide-react";
import CertificatesPanel from "@/components/CertificatesPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createStation, deleteCompanyDocument, deleteStation,
  listCompanyDocuments, listStationCertificates, listStationPhotos,
  listStations, updateStation, uploadCompanyDocument, uploadStationPhotos,
  uploadStationCertificate,
} from "@/lib/api";

const BLANK_ROW = { parameter: "", technique: "", sn: "", mdl_ugm3: "" };

function LabCard({ lab, onChanged }) {
  const [name, setName] = useState(lab.name);
  const [code, setCode] = useState(lab.code || "");
  const [rows, setRows] = useState(lab.instruments || []);
  const [busy, setBusy] = useState(false);
  const [photos, setPhotos] = useState([]);
  const [certs, setCerts] = useState([]);
  const [certNo, setCertNo] = useState("");
  const [certDate, setCertDate] = useState("");
  const [certDue, setCertDue] = useState("");
  const isNoise = lab.kind === "noise";

  useEffect(() => {
    listStationPhotos(lab.id).then(setPhotos).catch(() => setPhotos([]));
    listStationCertificates(lab.id).then(setCerts).catch(() => setCerts([]));
  }, [lab.id]);

  const addCert = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await uploadStationCertificate(lab.id, file, {
        cert_number: certNo,
        cert_date: certDate,
        cert_due_date: certDue,
        cert_model_sn: rows[0]?.sn || lab.code || "",
      });
      setCerts(await listStationCertificates(lab.id));
      setCertNo(""); setCertDate(""); setCertDue("");
      toast.success("Certificate stored — reports using this equipment will include it");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      e.target.value = "";
    }
  };

  const addPhotos = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    try {
      await uploadStationPhotos(lab.id, files);
      setPhotos(await listStationPhotos(lab.id));
      toast.success("Photograph saved — it will appear in every report using this equipment");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      e.target.value = "";
    }
  };

  const set = (i, k) => (e) =>
    setRows((r) => r.map((row, j) => (j === i ? { ...row, [k]: e.target.value } : row)));

  const save = async () => {
    setBusy(true);
    try {
      await updateStation(lab.id, {
        name, code,
        instruments: rows.filter((r) => r.parameter?.trim()).map((r) => ({
          ...r,
          mdl_ugm3: r.mdl_ugm3 === "" || r.mdl_ugm3 == null
            ? null : Number(r.mdl_ugm3),
        })),
      });
      toast.success(`${name} saved`);
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete ${lab.name}? Campaigns already using it keep their own copy.`))
      return;
    await deleteStation(lab.id);
    toast.success("Deleted");
    onChanged();
  };

  const certBlock = (
    <div className="pt-2 border-t border-border space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
          Calibration certificates
        </span>
        <span className="text-[11px] text-muted-foreground">
          {certs.length === 0
            ? "none yet — the report prints them in the calibration appendix"
            : `${certs.length} stored · a renewal is added, never replaced, so old reports stay reproducible`}
        </span>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label className="text-[11px]">Certificate number</Label>
          <Input value={certNo} onChange={(e) => setCertNo(e.target.value)}
                 placeholder="23-58393" className="rounded-sm h-8 w-[150px] text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Calibrated</Label>
          <Input type="date" value={certDate}
                 onChange={(e) => setCertDate(e.target.value)}
                 className="rounded-sm h-8 w-[150px] text-xs" />
        </div>
        <div className="space-y-1">
          <Label className="text-[11px]">Due</Label>
          <Input type="date" value={certDue}
                 onChange={(e) => setCertDue(e.target.value)}
                 className="rounded-sm h-8 w-[150px] text-xs" />
        </div>
        <label className="text-xs border border-border rounded-sm h-8 px-3 inline-flex items-center cursor-pointer hover:bg-secondary">
          Upload certificate (PDF or image)
          <input type="file" accept="application/pdf,image/*" hidden
                 onChange={addCert} />
        </label>
      </div>
      {certs.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {certs.map((c) => (
            <span key={c.id}
                  className="text-[11px] font-mono border border-border rounded-sm px-2 py-1">
              {c.cert_number || c.filename}
              {c.cert_date ? ` · ${c.cert_date}` : ""}
              {c.cert_due_date ? ` → ${c.cert_due_date}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );

  const photoStrip = (
    <div className="pt-2 border-t border-border">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
          Equipment photographs
        </span>
        <label className="text-[11px] text-primary hover:underline cursor-pointer">
          add
          <input type="file" accept="image/*" multiple hidden
                 onChange={addPhotos} />
        </label>
        {photos.length === 0 && (
          <span className="text-[11px] text-muted-foreground">
            none yet — printed in the report's methodology when added
          </span>
        )}
      </div>
      {photos.length > 0 && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {photos.map((p) => (
            <span key={p.id}
                  className="text-[11px] font-mono border border-border rounded-sm px-2 py-1">
              {p.filename}
            </span>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="border border-border rounded-sm p-4 space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">
            {isNoise ? "Meter name" : "Lab name"}
          </Label>
          <Input value={name} onChange={(e) => setName(e.target.value)}
                 className="rounded-sm h-9 w-[200px]" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Code / plate</Label>
          <Input value={code} onChange={(e) => setCode(e.target.value)}
                 className="rounded-sm h-9 w-[140px]" />
        </div>
        <Button variant="outline" className="rounded-sm h-9"
                onClick={() => setRows((r) => [...r, { ...BLANK_ROW }])}>
          <Plus className="w-4 h-4 mr-1.5" /> Add instrument
        </Button>
        <Button className="rounded-sm h-9" onClick={save} disabled={busy}>
          <Save className="w-4 h-4 mr-1.5" /> Save
        </Button>
        <Button variant="ghost" size="icon" className="rounded-sm h-9 w-9 ml-auto"
                onClick={remove}>
          <Trash2 className="w-4 h-4 text-muted-foreground" />
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No instruments yet.</p>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-12 gap-2 text-[11px] text-muted-foreground px-1">
            <div className="col-span-3">PARAMETER(S)</div>
            <div className="col-span-2">SERIAL NUMBER</div>
            <div className="col-span-5">INSTRUMENT / TECHNIQUE</div>
            <div className="col-span-1">MDL µg/m³</div>
          </div>
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center">
              <Input className="col-span-3 rounded-sm h-9 text-xs"
                     value={r.parameter || ""} onChange={set(i, "parameter")}
                     placeholder="SO2" />
              <Input className="col-span-2 rounded-sm h-9 text-xs font-mono"
                     value={r.sn || ""} onChange={set(i, "sn")} placeholder="1234" />
              <Input className="col-span-5 rounded-sm h-9 text-xs"
                     value={r.technique || ""} onChange={set(i, "technique")}
                     placeholder="T-100 (TELEDYNE) EQSA-0495-100" />
              <Input className="col-span-1 rounded-sm h-9 text-xs font-mono"
                     value={r.mdl_ugm3 ?? ""} onChange={set(i, "mdl_ugm3")}
                     placeholder="2.0" />
              <Button variant="ghost" size="icon" className="col-span-1 h-9 w-9"
                      onClick={() => setRows((x) => x.filter((_, j) => j !== i))}>
                <Trash2 className="w-4 h-4 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <CertificatesPanel lab={{ ...lab, name, instruments: rows }} />
      {certBlock}
      {photoStrip}
    </div>
  );
}

export default function StationsPage() {
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  // One registry, two kinds. An air record is a mobile laboratory of
  // analysers; a noise record is a sound level meter. They share the same
  // certificate handling and storage, so splitting them into two systems
  // would mean maintaining every fix twice.
  const [kind, setKind] = useState("air");

  const load = useCallback(() => {
    setLoading(true);
    return listStations(kind).then(setLabs)
      .catch(() => toast.error("Could not load equipment"))
      .finally(() => setLoading(false));
  }, [kind]);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!newName.trim()) return;
    await createStation({ name: newName.trim(), kind, instruments: [] });
    setNewName("");
    toast.success(kind === "noise" ? "Meter added" : "Lab created");
    load();
  };

  const isNoise = kind === "noise";
  const [licence, setLicence] = useState([]);

  useEffect(() => {
    listCompanyDocuments("license").then(setLicence).catch(() => setLicence([]));
  }, []);

  const addLicence = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    try {
      await uploadCompanyDocument(files, "license");
      setLicence(await listCompanyDocuments("license"));
      toast.success("Licence stored — every report will include it");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      e.target.value = "";
    }
  };

  const dropLicence = async (id) => {
    if (!window.confirm("Remove this page from the environmental licence?")) return;
    await deleteCompanyDocument(id);
    setLicence(await listCompanyDocuments("license"));
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Truck className="w-5 h-5 text-primary" /> Equipment
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {isNoise
            ? "Save each sound level meter once with its serial number, its calibration certificate and a photograph. Select it on a noise campaign and the report takes the meter details, the certificate and the photograph automatically."
            : "Save each mobile laboratory once with its analysers and serial numbers. Load a lab into any campaign and its instruments are printed in Table 4 of that report."}
        </p>
      </header>

      <div className="inline-flex rounded-sm border border-border overflow-hidden">
        {[["air", "Air — mobile labs"], ["noise", "Noise — sound level meters"]]
          .map(([k, label]) => (
          <button
            key={k}
            onClick={() => setKind(k)}
            data-testid={`equipment-kind-${k}`}
            className={`px-3 h-9 text-xs transition-colors ${
              kind === k
                ? "bg-primary text-primary-foreground"
                : "bg-background hover:bg-secondary"}`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">
            {isNoise ? "New meter name" : "New lab name"}
          </Label>
          <Input value={newName} onChange={(e) => setNewName(e.target.value)}
                 placeholder={isNoise ? "Cirrus CR:171B" : "Mobile Lab 1"}
                 className="rounded-sm h-9 w-[240px]" />
        </div>
        <Button className="rounded-sm h-9" onClick={add}>
          <Plus className="w-4 h-4 mr-1.5" />
          {isNoise ? "Add meter" : "Add lab"}
        </Button>
      </div>

      <div className="border border-border rounded-sm p-4 space-y-2">
        <h3 className="text-sm font-semibold">
          Environmental licence for the institution
        </h3>
        <p className="text-[11px] text-muted-foreground">
          Uploaded once for the company, not per job. Every report — air and
          noise — prints it as the environmental licence appendix. A campaign
          that carries its own licence attachment overrides this.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs border border-border rounded-sm h-8 px-3 inline-flex items-center cursor-pointer hover:bg-secondary">
            Upload licence (PDF or image)
            <input type="file" accept="application/pdf,image/*" multiple hidden
                   onChange={addLicence} />
          </label>
          {licence.length === 0 ? (
            <span className="text-[11px] text-muted-foreground">
              none stored — the appendix is omitted until one is added
            </span>
          ) : licence.map((d) => (
            <span key={d.id}
                  className="text-[11px] font-mono border border-border rounded-sm px-2 py-1 inline-flex items-center gap-2">
              {d.filename}
              <button onClick={() => dropLicence(d.id)}
                      className="text-muted-foreground hover:text-destructive">×</button>
            </span>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : labs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {isNoise
            ? "No sound level meters yet — add your first one above."
            : "No labs yet — add your first one above."}
        </p>
      ) : (
        <div className="space-y-4">
          {labs.map((l) => <LabCard key={l.id} lab={l} onChanged={load} />)}
        </div>
      )}
    </div>
  );
}
