import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Save, Trash2, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  listStations, loadStationIntoCampaign, updateCampaign,
} from "@/lib/api";

const BLANK = { parameter: "", technique: "", sn: "", calibration_date: "" };

export default function InstrumentsPanel({ campaign, onSaved }) {
  const [rows, setRows] = useState([]);
  const [stations, setStations] = useState([]);
  const [stationId, setStationId] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRows(campaign?.instruments?.length ? campaign.instruments : []);
    setStationId(campaign?.station_id || "");
  }, [campaign]);

  useEffect(() => {
    listStations().then(setStations).catch(() => {});
  }, []);

  const set = (i, key) => (e) =>
    setRows((r) => r.map((row, j) =>
      j === i ? { ...row, [key]: e.target.value } : row));

  const addRow = () => setRows((r) => [...r, { ...BLANK }]);
  const removeRow = (i) => setRows((r) => r.filter((_, j) => j !== i));

  const loadLab = async (id) => {
    setStationId(id);
    try {
      const data = await loadStationIntoCampaign(campaign.id, id);
      setRows(data.instruments || []);
      toast.success(`Loaded ${data.station} — ${data.instruments.length} instruments`);
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load the lab");
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      await updateCampaign(campaign.id, {
        instruments: rows.filter((r) => r.parameter?.trim()),
      });
      toast.success("Instruments saved — Table 4 will use these");
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-border rounded-sm p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Truck className="w-4 h-4 text-primary" /> Instruments (Table 4)
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          These rows are printed in the report as the equipment used for this
          campaign. Load one of your mobile labs, then edit if an analyser was
          swapped.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">Load from mobile lab</Label>
          <Select value={stationId} onValueChange={loadLab}>
            <SelectTrigger className="w-[240px] rounded-sm h-9">
              <SelectValue placeholder="Select a mobile lab…" />
            </SelectTrigger>
            <SelectContent>
              {stations.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}{s.code ? ` · ${s.code}` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" className="rounded-sm h-9" onClick={addRow}>
          <Plus className="w-4 h-4 mr-1.5" /> Add row
        </Button>
        <Button className="rounded-sm h-9 ml-auto" onClick={save} disabled={busy}>
          <Save className="w-4 h-4 mr-1.5" /> Save instruments
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No instruments set — the report will fall back to the default list.
          Load a mobile lab above to fix that.
        </p>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-12 gap-2 text-[11px] text-muted-foreground px-1">
            <div className="col-span-3">PARAMETER(S)</div>
            <div className="col-span-2">SERIAL NUMBER</div>
            <div className="col-span-6">INSTRUMENT / TECHNIQUE</div>
            <div className="col-span-1" />
          </div>
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center">
              <Input className="col-span-3 rounded-sm h-9 text-xs"
                     value={r.parameter || ""} onChange={set(i, "parameter")}
                     placeholder="SO2  /  NO, NO2, NOX" />
              <Input className="col-span-2 rounded-sm h-9 text-xs font-mono"
                     value={r.sn || ""} onChange={set(i, "sn")}
                     placeholder="1234" />
              <Input className="col-span-6 rounded-sm h-9 text-xs"
                     value={r.technique || ""} onChange={set(i, "technique")}
                     placeholder="T-100 (TELEDYNE) EQSA-0495-100" />
              <Button variant="ghost" size="icon"
                      className="col-span-1 h-9 w-9 rounded-sm"
                      onClick={() => removeRow(i)}>
                <Trash2 className="w-4 h-4 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
