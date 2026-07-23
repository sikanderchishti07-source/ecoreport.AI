import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Save, Trash2, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createStation, deleteStation, listStations, updateStation,
} from "@/lib/api";

const BLANK_ROW = { parameter: "", technique: "", sn: "", mdl_ugm3: "" };

function LabCard({ lab, onChanged }) {
  const [name, setName] = useState(lab.name);
  const [code, setCode] = useState(lab.code || "");
  const [rows, setRows] = useState(lab.instruments || []);
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="border border-border rounded-sm p-4 space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">Lab name</Label>
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
    </div>
  );
}

export default function StationsPage() {
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");

  const load = () =>
    listStations().then(setLabs)
      .catch(() => toast.error("Could not load labs"))
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const add = async () => {
    if (!newName.trim()) return;
    await createStation({ name: newName.trim(), instruments: [] });
    setNewName("");
    toast.success("Lab created");
    load();
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Truck className="w-5 h-5 text-primary" /> Mobile Labs
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Save each mobile laboratory once with its analysers and serial numbers.
          Load a lab into any campaign and its instruments are printed in Table 4
          of that report.
        </p>
      </header>

      <div className="flex items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">New lab name</Label>
          <Input value={newName} onChange={(e) => setNewName(e.target.value)}
                 placeholder="Mobile Lab 1" className="rounded-sm h-9 w-[240px]" />
        </div>
        <Button className="rounded-sm h-9" onClick={add}>
          <Plus className="w-4 h-4 mr-1.5" /> Add lab
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : labs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No labs yet — add your first one above.
        </p>
      ) : (
        <div className="space-y-4">
          {labs.map((l) => <LabCard key={l.id} lab={l} onChanged={load} />)}
        </div>
      )}
    </div>
  );
}
