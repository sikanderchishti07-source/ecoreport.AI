import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, CheckCircle2, FileText, Loader2, Upload, XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  attachmentFileUrl, deleteAttachment, listStationCertificates,
  uploadStationCertificate,
} from "@/lib/api";

/** Accept the handful of date formats operators actually type. */
function parseDate(v) {
  if (!v) return null;
  const s = String(v).trim();
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (iso) return new Date(+iso[1], +iso[2] - 1, +iso[3]);
  const dmy = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(s);
  if (dmy) return new Date(+dmy[3], +dmy[2] - 1, +dmy[1]);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

const DAY = 86400000;

/** Validity of a certificate relative to today. */
function validity(cert) {
  const due = parseDate(cert.cert_due_date);
  if (!due) return { tone: "unknown", label: "no due date", days: null };
  const days = Math.round((due.getTime() - Date.now()) / DAY);
  if (days < 0) return { tone: "expired", label: `expired ${-days} d ago`, days };
  if (days <= 60) return { tone: "soon", label: `expires in ${days} d`, days };
  return { tone: "valid", label: `valid — ${days} d left`, days };
}

const TONE = {
  valid: "bg-emerald-500/15 text-emerald-500",
  soon: "bg-amber-500/15 text-amber-500",
  expired: "bg-red-500/15 text-red-500",
  unknown: "bg-muted text-muted-foreground",
};

const BLANK = {
  instrument_sn: "", cert_number: "", cert_parameter: "",
  cert_model_sn: "", cert_date: "", cert_due_date: "", cert_result: "PASSED",
};

export default function CertificatesPanel({ lab }) {
  const [certs, setCerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(BLANK);
  const [file, setFile] = useState(null);
  const fileRef = useRef(null);
  // Memoised so it is a stable dependency for the coverage useMemo below;
  // a bare `lab.instruments || []` creates a new array on every render.
  const instruments = useMemo(() => lab.instruments || [], [lab.instruments]);

  // Only instruments that can be identified belong in the picker.
  //
  // The parent passes its live editing rows straight through, so the moment
  // someone presses "Add instrument" a blank row arrives here with no serial
  // number and no parameter. Rendering it produced a SelectItem with
  // value="", which Radix rejects by throwing — taking the whole page down
  // to a white screen. A half-typed row simply is not selectable yet.
  const selectable = useMemo(
    () => instruments.filter((i) => String(i.sn || i.parameter || "").trim()),
    [instruments],
  );

  const refresh = useCallback(() => {
    setLoading(true);
    listStationCertificates(lab.id)
      .then(setCerts)
      .catch(() => toast.error("Could not load certificates"))
      .finally(() => setLoading(false));
  }, [lab.id]);

  useEffect(() => { refresh(); }, [refresh]);

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target?.value ?? e }));

  /** Picking the analyser fills in what we already know about it. */
  const pickInstrument = (sn) => {
    const i = instruments.find((x) => x.sn === sn);
    setForm((f) => ({
      ...f,
      instrument_sn: sn,
      cert_parameter: f.cert_parameter || i?.parameter || "",
      cert_model_sn: f.cert_model_sn
        || (i ? `${String(i.technique || "").split("(")[0].trim()} / ${i.sn}` : ""),
    }));
  };

  const upload = async () => {
    if (!file) return toast.error("Choose the certificate file first");
    if (!form.cert_number) return toast.error("Certificate number is required");
    setBusy(true);
    try {
      await uploadStationCertificate(lab.id, file, form);
      toast.success(`Certificate ${form.cert_number} saved to ${lab.name}`);
      setForm(BLANK);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Remove this certificate from the lab?")) return;
    try {
      await deleteAttachment(id);
      refresh();
    } catch {
      toast.error("Could not remove the certificate");
    }
  };

  /** Newest certificate per analyser, for the coverage summary. */
  const coverage = useMemo(() => {
    const best = {};
    certs.forEach((c) => {
      const sn = c.instrument_sn || "—";
      const d = parseDate(c.cert_date)?.getTime() || 0;
      if (!best[sn] || d > best[sn]._d) best[sn] = { ...c, _d: d };
    });
    return instruments.map((i) => ({
      instrument: i,
      cert: best[i.sn] || null,
    }));
  }, [certs, instruments]);

  const attention = coverage.filter(
    (c) => !c.cert || ["expired", "soon"].includes(validity(c.cert).tone)
  ).length;

  return (
    <div className="border border-border rounded-sm p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" /> Calibration certificates
          <Badge variant="outline" className="rounded-sm font-mono">
            {certs.length}
          </Badge>
          {attention > 0 && (
            <Badge className="rounded-sm bg-amber-500/15 text-amber-500 border-0">
              <AlertTriangle className="w-3.5 h-3.5 mr-1" />
              {attention} need attention
            </Badge>
          )}
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Certificates belong to the analyser, so upload each one once here.
          Every campaign that uses {lab.name} picks up the certificate that was
          valid during its own monitoring period — renewing never overwrites an
          older record, so past reports stay reproducible.
        </p>
      </div>

      {/* coverage per analyser */}
      {instruments.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {coverage.map(({ instrument, cert }) => {
            const v = cert ? validity(cert) : null;
            return (
              <div key={instrument.sn || instrument.parameter}
                   className="flex items-center gap-2.5 bg-secondary/40 rounded-sm px-3 py-2">
                {cert ? (
                  v.tone === "valid"
                    ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    : <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                ) : (
                  <XCircle className="w-4 h-4 text-muted-foreground shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium truncate">
                    {instrument.parameter}
                    <span className="text-muted-foreground font-mono">
                      {" "}S/N {instrument.sn || "—"}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {cert ? `${cert.cert_number} · due ${cert.cert_due_date || "—"}`
                          : "no certificate on file"}
                  </div>
                </div>
                {v && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-sm whitespace-nowrap ${TONE[v.tone]}`}>
                    {v.label}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* upload form */}
      <div className="border-t border-border pt-3 space-y-3">
        <p className="text-xs font-medium">Add a certificate</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
          <div className="space-y-1.5">
            <Label className="text-xs">Analyser</Label>
            <Select value={form.instrument_sn} onValueChange={pickInstrument}>
              <SelectTrigger className="rounded-sm h-9 text-xs">
                <SelectValue placeholder="Select analyser…" />
              </SelectTrigger>
              <SelectContent>
                {selectable.length === 0 ? (
                  <div className="px-2 py-2 text-xs text-muted-foreground">
                    Name an instrument and save before attaching a certificate.
                  </div>
                ) : (
                  selectable.map((i) => {
                    const value = String(i.sn || i.parameter).trim();
                    return (
                      <SelectItem key={value} value={value}>
                        {i.parameter || "(unnamed)"} — S/N {i.sn || "—"}
                      </SelectItem>
                    );
                  })
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Certificate number *</Label>
            <Input className="rounded-sm h-9 text-xs" value={form.cert_number}
                   onChange={set("cert_number")} placeholder="23-58893" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Parameter</Label>
            <Input className="rounded-sm h-9 text-xs" value={form.cert_parameter}
                   onChange={set("cert_parameter")} placeholder="Sulphur Dioxide (SO₂)" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Model / serial</Label>
            <Input className="rounded-sm h-9 text-xs" value={form.cert_model_sn}
                   onChange={set("cert_model_sn")} placeholder="T100 / 3434" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Calibration date</Label>
            <Input type="date" className="rounded-sm h-9 text-xs"
                   value={form.cert_date} onChange={set("cert_date")} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Due date</Label>
            <Input type="date" className="rounded-sm h-9 text-xs"
                   value={form.cert_due_date} onChange={set("cert_due_date")} />
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <Label className="text-xs">Result</Label>
            <Input className="rounded-sm h-9 text-xs" value={form.cert_result}
                   onChange={set("cert_result")} placeholder="PASSED (2.5 ppm SO₂)" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Certificate file *</Label>
            <Input ref={fileRef} type="file" accept="image/*,application/pdf"
                   className="rounded-sm h-9 text-xs"
                   onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </div>
        </div>
        <Button className="rounded-sm h-9" onClick={upload} disabled={busy}>
          {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <Upload className="w-4 h-4 mr-1.5" />}
          Save certificate
        </Button>
      </div>

      {/* what is on file */}
      {loading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : certs.length > 0 && (
        <div className="border-t border-border pt-3">
          <p className="text-xs font-medium mb-2">On file</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Certificate</TableHead>
                <TableHead className="text-xs">Parameter</TableHead>
                <TableHead className="text-xs">S/N</TableHead>
                <TableHead className="text-xs">Calibrated</TableHead>
                <TableHead className="text-xs">Due</TableHead>
                <TableHead className="text-xs">Status</TableHead>
                <TableHead className="text-xs text-right">File</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {certs.map((c) => {
                const v = validity(c);
                return (
                  <TableRow key={c.id}>
                    <TableCell className="text-xs font-mono">{c.cert_number || "—"}</TableCell>
                    <TableCell className="text-xs">{c.cert_parameter || "—"}</TableCell>
                    <TableCell className="text-xs font-mono">{c.instrument_sn || "—"}</TableCell>
                    <TableCell className="text-xs">{c.cert_date || "—"}</TableCell>
                    <TableCell className="text-xs">{c.cert_due_date || "—"}</TableCell>
                    <TableCell>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-sm ${TONE[v.tone]}`}>
                        {v.label}
                      </span>
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <a href={attachmentFileUrl(c.id)}
                         className="text-xs text-primary hover:underline">view</a>
                      <button onClick={() => remove(c.id)}
                              className="text-xs text-muted-foreground hover:text-red-400 ml-3">
                        remove
                      </button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
