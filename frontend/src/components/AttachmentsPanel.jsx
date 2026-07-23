import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { FileText, Image as ImageIcon, MapPin, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  attachmentFileUrl, deleteAttachment, listAttachments, updateAttachment,
  uploadAttachments,
} from "@/lib/api";

const SECTIONS = [
  { kind: "site_photo", title: "Field photos", icon: ImageIcon,
    hint: "Four station photos taken on site — printed as a 2×2 grid (Figure 2)." },
  { kind: "calibration", title: "Calibration certificates", icon: FileText,
    hint: "Images or PDFs. Link each one to its analyser so Appendix 3 states the serial number." },
  { kind: "license", title: "Environmental licence", icon: FileText,
    hint: "The provider's licence — printed in Appendix 4." },
  { kind: "site_map", title: "Site map override", icon: MapPin,
    hint: "Optional. Upload your own satellite image to replace the automatic map (Figure 1)." },
  { kind: "cover_photo", title: "Cover photo", icon: ImageIcon,
    hint: "Optional image for the report cover." },
];

function Section({ campaignId, section, items, instruments, onChange }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [sn, setSn] = useState("");
  const Icon = section.icon;

  const pick = async (files) => {
    if (!files?.length) return;
    setBusy(true);
    try {
      await uploadAttachments(campaignId, section.kind, files,
        section.kind === "calibration" && sn ? { instrument_sn: sn } : {});
      toast.success(`${files.length} file(s) uploaded`);
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async (id) => {
    try {
      await deleteAttachment(id);
      onChange();
    } catch {
      toast.error("Delete failed");
    }
  };

  const setCaption = async (id, caption) => {
    try {
      await updateAttachment(id, { caption });
    } catch {
      toast.error("Could not save caption");
    }
  };

  const setInstrument = async (id, instrument_sn) => {
    try {
      await updateAttachment(id, { instrument_sn });
      toast.success("Linked to instrument");
      onChange();
    } catch {
      toast.error("Could not link");
    }
  };

  return (
    <div className="border border-border rounded-sm p-4">
      <div className="flex items-start gap-2">
        <Icon className="w-4 h-4 text-primary mt-0.5" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold">
            {section.title}{" "}
            <Badge variant="outline" className="rounded-sm font-mono ml-1">
              {items.length}
            </Badge>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">{section.hint}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {section.kind === "calibration" && instruments.length > 0 && (
          <Select value={sn} onValueChange={setSn}>
            <SelectTrigger className="w-[280px] rounded-sm h-9 text-xs">
              <SelectValue placeholder="Link upload to analyser (optional)…" />
            </SelectTrigger>
            <SelectContent>
              {instruments.map((i) => (
                <SelectItem key={i.sn || i.parameter} value={i.sn || i.parameter}>
                  {i.parameter} — S/N {i.sn || "—"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <input
          ref={inputRef}
          type="file"
          multiple={section.kind !== "site_map" && section.kind !== "cover_photo"}
          accept="image/*,application/pdf"
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />
        <Button
          variant="outline"
          className="rounded-sm h-9"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          <Upload className="w-4 h-4 mr-1.5" />
          {busy ? "Uploading…" : "Choose files"}
        </Button>
      </div>

      {items.length > 0 && (
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
          {items.map((a) => (
            <div key={a.id} className="border border-border rounded-sm p-2 space-y-1.5">
              <div className="aspect-[4/3] bg-secondary/50 rounded-sm overflow-hidden flex items-center justify-center">
                <img
                  src={attachmentFileUrl(a.id)}
                  alt={a.filename}
                  className="object-cover w-full h-full"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
              </div>
              <Input
                defaultValue={a.caption || ""}
                placeholder="Caption…"
                className="rounded-sm h-8 text-[11px]"
                onBlur={(e) => setCaption(a.id, e.target.value)}
              />
              {section.kind === "calibration" && (
                <Select
                  value={a.instrument_sn || ""}
                  onValueChange={(v) => setInstrument(a.id, v)}
                >
                  <SelectTrigger className="rounded-sm h-8 text-[11px]">
                    <SelectValue placeholder="Not linked" />
                  </SelectTrigger>
                  <SelectContent>
                    {instruments.map((i) => (
                      <SelectItem key={i.sn || i.parameter} value={i.sn || i.parameter}>
                        {i.parameter} — S/N {i.sn || "—"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <button
                onClick={() => remove(a.id)}
                className="text-[11px] text-muted-foreground hover:text-red-400 inline-flex items-center gap-1"
              >
                <Trash2 className="w-3 h-3" /> Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AttachmentsPanel({ campaign }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const instruments = campaign?.instruments || [];

  const refresh = useCallback(() => {
    setLoading(true);
    listAttachments(campaign.id)
      .then(setItems)
      .catch(() => toast.error("Could not load attachments"))
      .finally(() => setLoading(false));
  }, [campaign.id]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="space-y-4">
      {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
      {SECTIONS.map((s) => (
        <Section
          key={s.kind}
          campaignId={campaign.id}
          section={s}
          items={items.filter((i) => i.kind === s.kind)}
          instruments={instruments}
          onChange={refresh}
        />
      ))}
    </div>
  );
}
