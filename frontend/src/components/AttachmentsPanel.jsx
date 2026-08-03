import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Check, ChevronLeft, ChevronRight, FileText, Image as ImageIcon, ImageOff,
  MapPin, Trash2, Upload,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  clearCoverPhoto, deleteAttachment, listAttachments, listCoverPhotos,
  selectCoverPhoto, updateAttachment, uploadAttachments,
} from "@/lib/api";
import AuthImage from "@/components/AuthImage";

// cover_photo is absent here: it is chosen from the shared library below
// rather than uploaded per campaign.
const SECTIONS = [
  { kind: "site_photo", title: "Field photos", icon: ImageIcon, orderable: true,
    hint: "Four station photos taken on site — printed as a 2×2 grid (Figure 2).",
    orderHint: "Position 1 prints top-left, 2 top-right, 3 bottom-left, 4 bottom-right." },
  { kind: "calibration", title: "Calibration certificates", icon: FileText, orderable: true,
    hint: "Images or PDFs. Link each one to its analyser so Appendix 3 states the serial number.",
    orderHint: "Certificates print in this order in Appendix 3." },
  { kind: "license", title: "Environmental licence", icon: FileText, orderable: true,
    hint: "The provider's licence — printed in Appendix 4.",
    orderHint: "Pages print in this order in Appendix 4." },
  { kind: "site_map", title: "Site map override", icon: MapPin, orderable: false,
    hint: "Optional. Upload your own satellite image to replace the automatic map (Figure 1)." },
];

function Section({ campaignId, section, items, instruments, onChange }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [sn, setSn] = useState("");
  // Local copy so an arrow click moves the tile immediately rather than after
  // a round trip. Re-synced whenever the parent refetches.
  const [ordered, setOrdered] = useState(items);
  const [reordering, setReordering] = useState(false);
  const Icon = section.icon;

  useEffect(() => { setOrdered(items); }, [items]);

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

  /**
   * Swap a tile with its neighbour and write every position back.
   *
   * Rewriting all of them rather than just the two that moved also repairs
   * files uploaded before ordering existed, whose stored positions may be
   * duplicated or absent.
   */
  const move = async (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= ordered.length) return;
    const previous = ordered;
    const next = [...ordered];
    [next[index], next[target]] = [next[target], next[index]];
    setOrdered(next);
    setReordering(true);
    try {
      await Promise.all(next.map((a, i) => updateAttachment(a.id, { order: i })));
    } catch {
      toast.error("Could not save the new order");
      setOrdered(previous);
    } finally {
      setReordering(false);
    }
  };

  const canOrder = section.orderable && ordered.length > 1;

  return (
    <div className="border border-border rounded-sm p-4">
      <div className="flex items-start gap-2">
        <Icon className="w-4 h-4 text-primary mt-0.5" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold">
            {section.title}{" "}
            <Badge variant="outline" className="rounded-sm font-mono ml-1">
              {ordered.length}
            </Badge>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">{section.hint}</p>
          {canOrder && (
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {section.orderHint} Use the arrows on each tile to change the order.
            </p>
          )}
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
          multiple={section.kind !== "site_map"}
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

      {ordered.length > 0 && (
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
          {ordered.map((a, idx) => (
            <div
              key={a.id}
              data-testid={`attachment-${section.kind}-${idx}`}
              className="border border-border rounded-sm p-2 space-y-1.5"
            >
              <div className="relative aspect-[4/3] bg-secondary/50 rounded-sm overflow-hidden flex items-center justify-center">
                {/* the file route needs a Bearer token, which a plain <img>
                    cannot send — AuthImage fetches it and supplies a blob */}
                <AuthImage
                  attachmentId={a.id}
                  alt={a.filename}
                  className="object-cover w-full h-full"
                />
                {canOrder && (
                  <span className="absolute top-1 left-1 text-[10px] font-mono bg-background/85 border border-border rounded-sm px-1.5 py-0.5">
                    {idx + 1}
                  </span>
                )}
              </div>

              {canOrder && (
                <div className="flex items-center justify-between">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="rounded-sm h-7 px-2"
                    disabled={idx === 0 || reordering}
                    onClick={() => move(idx, -1)}
                    aria-label="Move earlier"
                    data-testid={`attachment-move-back-${a.id}`}
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </Button>
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Position {idx + 1}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="rounded-sm h-7 px-2"
                    disabled={idx === ordered.length - 1 || reordering}
                    onClick={() => move(idx, 1)}
                    aria-label="Move later"
                    data-testid={`attachment-move-fwd-${a.id}`}
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Button>
                </div>
              )}

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

/**
 * Choose which library photograph this report's cover uses.
 *
 * The photographs themselves are held once under Cover Photos; a campaign
 * only records which one it wants. Nothing selected means the standard cover,
 * which is what every campaign did before this existed.
 */
function CoverPicker({ campaignId, selectedSourceId, onChange }) {
  const [library, setLibrary] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listCoverPhotos()
      .then(setLibrary)
      .catch(() => toast.error("Could not load the cover photo library"))
      .finally(() => setLoading(false));
  }, []);

  const choose = async (photo) => {
    setSaving(true);
    try {
      if (selectedSourceId === photo.id) {
        await clearCoverPhoto(campaignId);
        toast.success("Back to the standard cover");
      } else {
        await selectCoverPhoto(campaignId, photo.id);
        toast.success(`Cover set to "${photo.caption || photo.filename}"`);
      }
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not set the cover");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-border rounded-sm p-4">
      <div className="flex items-start gap-2">
        <ImageIcon className="w-4 h-4 text-primary mt-0.5" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold">Report cover</h3>
          <p className="text-xs text-muted-foreground mt-1">
            Click a photo to use it on this report's cover. Click it again to
            go back to the standard cover.
          </p>
        </div>
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground mt-3">Loading…</p>
      ) : library.length === 0 ? (
        <div className="mt-3 border border-dashed border-border rounded-sm p-6 text-center">
          <ImageOff className="w-5 h-5 mx-auto text-muted-foreground mb-2" />
          <p className="text-xs text-muted-foreground">
            The library is empty. Add photographs under{" "}
            <Link to="/cover-photos" className="text-primary underline decoration-dotted">
              Cover Photos
            </Link>{" "}
            and they will appear here for every campaign.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
            {library.map((p) => {
              const active = selectedSourceId === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  disabled={saving}
                  onClick={() => choose(p)}
                  data-testid={`cover-pick-${p.id}`}
                  aria-pressed={active}
                  className={`relative text-left rounded-sm overflow-hidden border transition-colors ${
                    active
                      ? "border-2 border-emerald-500"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="aspect-[4/3] bg-secondary/50 flex items-center justify-center">
                    <AuthImage
                      attachmentId={p.id}
                      alt={p.caption || p.filename}
                      className="object-cover w-full h-full"
                    />
                  </div>
                  {active && (
                    <span className="absolute top-1.5 right-1.5 inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-500">
                      <Check className="w-3 h-3 text-white" />
                    </span>
                  )}
                  <span
                    className={`block px-2 py-1.5 text-[11px] truncate ${
                      active ? "font-medium" : "text-muted-foreground"
                    }`}
                  >
                    {p.caption || p.filename}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2.5">
            {selectedSourceId
              ? "This report will use the ticked photo."
              : "Nothing selected — this report uses the standard cover image."}
          </p>
        </>
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

  const cover = items.find((i) => i.kind === "cover_photo");

  return (
    <div className="space-y-4">
      {loading && <p className="text-xs text-muted-foreground">Loading…</p>}

      <CoverPicker
        campaignId={campaign.id}
        selectedSourceId={cover?.source_id || null}
        onChange={refresh}
      />

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
