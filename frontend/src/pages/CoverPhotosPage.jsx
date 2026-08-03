import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ImagePlus, Loader2, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import AuthImage from "@/components/AuthImage";
import {
  deleteCoverPhoto, listCoverPhotos, updateAttachment, uploadCoverPhotos,
} from "@/lib/api";

export default function CoverPhotosPage() {
  const inputRef = useRef(null);
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    setLoading(true);
    listCoverPhotos()
      .then(setPhotos)
      .catch(() => toast.error("Could not load cover photos"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const pick = async (files) => {
    if (!files?.length) return;
    setBusy(true);
    try {
      await uploadCoverPhotos(files);
      toast.success(`${files.length} photo(s) added`);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async (photo) => {
    try {
      await deleteCoverPhoto(photo.id);
      toast.success("Photo removed from the library");
      refresh();
    } catch {
      toast.error("Delete failed");
    }
  };

  const rename = async (id, caption) => {
    try {
      await updateAttachment(id, { caption });
    } catch {
      toast.error("Could not save the name");
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cover photos</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Photographs available to every campaign. Upload them once here,
            then each campaign chooses which one appears on its report cover,
            under Attachments.
          </p>
        </div>
        <div>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="image/*"
            className="hidden"
            onChange={(e) => pick(e.target.files)}
          />
          <Button
            className="rounded-sm h-9"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            data-testid="cover-photos-upload"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
            ) : (
              <Upload className="w-4 h-4 mr-1.5" />
            )}
            {busy ? "Uploading…" : "Add photos"}
          </Button>
        </div>
      </header>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : photos.length === 0 ? (
        <div className="border border-dashed border-border rounded-sm p-12 text-center">
          <ImagePlus className="w-6 h-6 mx-auto text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">
            No cover photos yet. Add a few and every campaign can pick from them.
          </p>
          <Button
            variant="outline"
            className="mt-4 rounded-sm"
            onClick={() => inputRef.current?.click()}
          >
            <Upload className="w-4 h-4 mr-1.5" /> Add photos
          </Button>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="rounded-sm font-mono">
              {photos.length}
            </Badge>
            <span className="text-xs text-muted-foreground">
              in the library
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {photos.map((p) => (
              <div
                key={p.id}
                className="border border-border rounded-sm p-2 space-y-2"
                data-testid={`cover-photo-${p.id}`}
              >
                <div className="aspect-[4/3] bg-secondary/50 rounded-sm overflow-hidden flex items-center justify-center">
                  <AuthImage
                    attachmentId={p.id}
                    alt={p.caption || p.filename}
                    className="object-cover w-full h-full"
                  />
                </div>
                <Input
                  defaultValue={p.caption || ""}
                  placeholder="Name this photo…"
                  className="rounded-sm h-8 text-[11px]"
                  onBlur={(e) => rename(p.id, e.target.value)}
                />
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <button className="text-[11px] text-muted-foreground hover:text-red-400 inline-flex items-center gap-1">
                      <Trash2 className="w-3 h-3" /> Remove
                    </button>
                  </AlertDialogTrigger>
                  <AlertDialogContent className="rounded-sm">
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        Remove this photo from the library?
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        Any campaign currently using it goes back to the
                        standard cover image. Reports already generated are
                        not affected.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel className="rounded-sm">
                        Cancel
                      </AlertDialogCancel>
                      <AlertDialogAction
                        className="rounded-sm bg-red-600 hover:bg-red-500"
                        onClick={() => remove(p)}
                      >
                        Remove
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
