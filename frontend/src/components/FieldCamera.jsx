/**
 * The field camera.
 *
 * A live preview with a compass, and a stamp burned into the photograph as it
 * is taken: date, time, coordinates with their accuracy, the bearing the phone
 * was facing, and the site. It replaces the separate timestamp-camera app —
 * with two things that app cannot know, because it is not part of the survey:
 * which site this is, and which way the operator was pointing.
 *
 * The time is taken from the phone at the moment of capture and cannot be
 * typed. That is the whole worth of a stamped photograph: if the time can be
 * chosen, the stamp proves nothing, and every other photograph becomes
 * arguable too. The *format* is chosen; the value is not.
 *
 * The bearing is recorded as the number the compass reported, not as the label
 * the operator picked from a list. A photograph labelled "north" and taken
 * facing 095° is a small untruth that nobody would catch later, so the stamp
 * carries the reading and the label separately.
 *
 * Everything degrades. No camera permission falls back to the phone's own
 * camera app through a file input; no compass simply omits the bearing rather
 * than inventing one; no position omits the coordinates. A missing line is
 * obvious. A wrong one is not.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, Compass, Images, Loader2, RotateCcw, X } from "lucide-react";

/** Cardinal name for a bearing — for the label, never instead of the number. */
export function cardinal(deg) {
  if (deg == null || Number.isNaN(deg)) return null;
  const names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return names[Math.round(((deg % 360) + 360) % 360 / 22.5) % 16];
}

export const DATE_FORMATS = {
  long: { label: "11 Jul 2026", fmt: (d) => d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) },
  slash: { label: "11/07/2026", fmt: (d) => d.toLocaleDateString("en-GB") },
  iso: { label: "2026-07-11", fmt: (d) => d.toISOString().slice(0, 10) },
};

function timeStr(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default function FieldCamera({
  open, onClose, onCapture, view, site, coords, dateFormat = "long",
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [denied, setDenied] = useState(false);
  const [heading, setHeading] = useState(null);
  const [shooting, setShooting] = useState(false);

  // ---- live preview -------------------------------------------------------
  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const s = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } },
          audio: false,
        });
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          await videoRef.current.play().catch(() => {});
        }
        setReady(true);
      } catch {
        // No permission, or a browser that will not do it: hand over to the
        // phone's own camera rather than leaving a dead button.
        setDenied(true);
      }
    })();
    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      setReady(false);
    };
  }, [open]);

  // ---- compass ------------------------------------------------------------
  const onOrient = useCallback((e) => {
    // iOS reports a true heading directly; elsewhere alpha is measured
    // anticlockwise from north, so it has to be turned round.
    const h = e.webkitCompassHeading != null
      ? e.webkitCompassHeading
      : (e.absolute && e.alpha != null ? 360 - e.alpha : null);
    if (h != null && !Number.isNaN(h)) setHeading((h % 360 + 360) % 360);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const need = typeof DeviceOrientationEvent !== "undefined"
      && typeof DeviceOrientationEvent.requestPermission === "function";
    if (!need) {
      window.addEventListener("deviceorientationabsolute", onOrient, true);
      window.addEventListener("deviceorientation", onOrient, true);
    }
    return () => {
      window.removeEventListener("deviceorientationabsolute", onOrient, true);
      window.removeEventListener("deviceorientation", onOrient, true);
    };
  }, [open, onOrient]);

  const askCompass = async () => {
    try {
      const ok = await DeviceOrientationEvent.requestPermission();
      if (ok === "granted") {
        window.addEventListener("deviceorientation", onOrient, true);
      } else {
        toast.error("Compass not allowed — the bearing will be left off");
      }
    } catch {
      toast.error("This phone will not share its compass");
    }
  };
  const needsCompassTap = typeof DeviceOrientationEvent !== "undefined"
    && typeof DeviceOrientationEvent.requestPermission === "function"
    && heading == null;

  // ---- the stamp ----------------------------------------------------------
  const stamp = (canvas, ctx, w, h) => {
    const now = new Date();
    const s = Math.min(w, h);
    const band = Math.round(s * 0.145);
    const pad = Math.round(s * 0.045);

    const g = ctx.createLinearGradient(0, h - band, 0, h);
    g.addColorStop(0, "rgba(6,16,26,0)");
    g.addColorStop(0.35, "rgba(6,16,26,0.62)");
    g.addColorStop(1, "rgba(6,16,26,0.90)");
    ctx.fillStyle = g;
    ctx.fillRect(0, h - band, w, band);
    ctx.fillStyle = "rgba(126,208,138,0.92)";
    ctx.fillRect(0, h - band, w, Math.max(2, Math.round(s * 0.004)));

    const F = (px, bold) =>
      `${bold ? "600 " : ""}${Math.round(px)}px ui-sans-serif, system-ui, -apple-system, sans-serif`;
    let y = h - band + Math.round(s * 0.052);

    ctx.textAlign = "left";
    ctx.fillStyle = "#ffffff";
    ctx.font = F(s * 0.050, true);
    ctx.fillText(
      `${(DATE_FORMATS[dateFormat] || DATE_FORMATS.long).fmt(now)}   ${timeStr(now)}`,
      pad, y,
    );

    y += Math.round(s * 0.040);
    ctx.fillStyle = "rgba(214,228,240,0.95)";
    ctx.font = F(s * 0.032);
    const parts = [];
    if (coords?.latitude) {
      parts.push(`${coords.latitude} N, ${coords.longitude} E`);
      if (coords.accuracy != null) parts.push(`±${coords.accuracy} m`);
    }
    if (heading != null) {
      parts.push(`${Math.round(heading)}° ${cardinal(heading)}`);
    }
    ctx.fillText(parts.join("   "), pad, y);

    y += Math.round(s * 0.032);
    ctx.fillStyle = "rgba(150,200,160,0.95)";
    ctx.font = F(s * 0.029);
    ctx.fillText([site, view].filter(Boolean).join("  ·  "), pad, y);

    ctx.textAlign = "right";
    ctx.fillStyle = "rgba(255,255,255,0.88)";
    ctx.font = F(s * 0.034, true);
    ctx.fillText("BSA.lab", w - pad, h - band + Math.round(s * 0.052));
  };

  const shoot = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setShooting(true);
    try {
      const w = video.videoWidth;
      const h = video.videoHeight;
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, w, h);
      stamp(canvas, ctx, w, h);
      const blob = await new Promise((res) =>
        canvas.toBlob(res, "image/jpeg", 0.9));
      if (!blob) throw new Error("no blob");
      const name = `${(view || "photo").toLowerCase().replace(/\s+/g, "-")}`
        + `-${Date.now()}.jpg`;
      onCapture(new File([blob], name, { type: "image/jpeg" }), {
        view, heading: heading == null ? null : Math.round(heading),
      });
      onClose();
    } catch {
      toast.error("Could not take the photograph — try again");
    } finally {
      setShooting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black text-white flex flex-col">
      <div className="flex items-center gap-3 px-4 py-3">
        <button type="button" onClick={onClose} aria-label="Close"
          className="rounded-lg border border-white/15 p-2">
          <X className="w-4 h-4" />
        </button>
        <div className="text-[13px]">
          <div className="font-semibold">{view || "Photograph"}</div>
          <div className="text-[11px] text-white/55">{site}</div>
        </div>
        <button type="button" onClick={() => fileRef.current?.click()}
          className="ml-auto rounded-lg border border-white/15 px-3 py-2 text-[12px]
                     inline-flex items-center gap-1.5">
          <Images className="w-3.5 h-3.5" /> Gallery
        </button>
      </div>

      <div className="relative flex-1 overflow-hidden bg-black">
        {!denied && (
          <video ref={videoRef} playsInline muted
            className="absolute inset-0 h-full w-full object-cover" />
        )}

        {/* compass */}
        <div className="absolute left-0 right-0 top-3 flex justify-center">
          <div className="rounded-full bg-black/45 backdrop-blur px-4 py-2
                          border border-white/12 flex items-center gap-2.5">
            <Compass className="w-4 h-4 text-emerald-300" />
            {heading == null ? (
              needsCompassTap ? (
                <button type="button" onClick={askCompass}
                  className="text-[12px] text-emerald-300">Turn on compass</button>
              ) : <span className="text-[12px] text-white/55">No compass</span>
            ) : (
              <span className="tabular-nums text-[15px] font-semibold">
                {String(Math.round(heading)).padStart(3, "0")}°
                <span className="ml-1.5 text-emerald-300">{cardinal(heading)}</span>
              </span>
            )}
          </div>
        </div>

        {/* the rose, so a bearing can be read at a glance */}
        {heading != null && (
          <div className="absolute left-1/2 top-20 -translate-x-1/2">
            <div className="relative h-24 w-24 rounded-full border border-white/15
                            bg-black/25 backdrop-blur-[2px]">
              <div className="absolute inset-0"
                style={{ transform: `rotate(${-heading}deg)` }}>
                {["N", "E", "S", "W"].map((c, i) => (
                  <span key={c}
                    className={`absolute left-1/2 -translate-x-1/2 text-[10px] font-semibold
                      ${c === "N" ? "text-rose-400" : "text-white/70"}`}
                    style={{
                      top: 6,
                      transformOrigin: "50% 42px",
                      transform: `rotate(${i * 90}deg)`,
                    }}>{c}</span>
                ))}
              </div>
              <div className="absolute left-1/2 top-1/2 h-8 w-[2px] -translate-x-1/2
                              -translate-y-full bg-emerald-300" />
              <div className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2
                              -translate-y-1/2 rounded-full bg-emerald-300" />
            </div>
          </div>
        )}

        {/* what will be written onto the picture */}
        <div className="absolute bottom-0 left-0 right-0 p-4
                        bg-gradient-to-t from-black/85 to-transparent">
          <div className="text-[15px] font-semibold tabular-nums">
            {(DATE_FORMATS[dateFormat] || DATE_FORMATS.long).fmt(new Date())}
            {"   "}{timeStr(new Date())}
          </div>
          <div className="text-[11.5px] text-white/70">
            {coords?.latitude
              ? `${coords.latitude} N, ${coords.longitude} E   ±${coords.accuracy} m`
              : "No position"}
            {heading != null && `   ${Math.round(heading)}° ${cardinal(heading)}`}
          </div>
          <div className="text-[11px] text-emerald-300/85">
            {[site, view].filter(Boolean).join("  ·  ")}
          </div>
        </div>

        {denied && (
          <div className="absolute inset-0 grid place-items-center p-6 text-center">
            <div>
              <Camera className="mx-auto mb-3 h-6 w-6 text-white/50" />
              <p className="text-[13px] text-white/75 mb-4">
                The camera is not available in the browser here.
              </p>
              <button type="button" onClick={() => fileRef.current?.click()}
                className="rounded-xl bg-white/10 border border-white/15 px-4 py-3 text-[13px]">
                Use the phone&rsquo;s camera instead
              </button>
              <p className="text-[11px] text-white/40 mt-3">
                Photographs taken that way keep their own stamp; ours is not added.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-center gap-8 py-6">
        <button type="button" onClick={() => setHeading(null)}
          aria-label="Reset compass"
          className="rounded-full border border-white/15 p-3 text-white/60">
          <RotateCcw className="w-4 h-4" />
        </button>
        <button type="button" onClick={shoot} disabled={!ready || shooting}
          aria-label="Take photograph"
          className="h-[74px] w-[74px] rounded-full border-4 border-white/85
                     bg-white/15 grid place-items-center disabled:opacity-40
                     active:scale-95 transition">
          {shooting
            ? <Loader2 className="w-6 h-6 animate-spin" />
            : <span className="h-[58px] w-[58px] rounded-full bg-white" />}
        </button>
        <span className="w-10" />
      </div>

      {/* gallery, and the fallback when the browser will not give us a preview */}
      <input ref={fileRef} type="file" accept="image/*" multiple className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          e.target.value = "";
          if (!files.length) return;
          // Left exactly as they are: they already carry the stamp from his
          // own camera, and a second stamp on top would be both ugly and
          // arguably a claim about a time we did not observe.
          files.forEach((f) => onCapture(f, { view, heading: null, fromGallery: true }));
          onClose();
        }} />
    </div>
  );
}
