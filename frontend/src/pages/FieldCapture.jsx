/**
 * Site capture — the page an operator opens on a phone at a monitoring site.
 *
 * It exists because of one repeated failure: the monitoring window was typed
 * from memory back at the office, the date picker shows the month first, and a
 * day and a month were swapped more than once — producing a 720-hour report at
 * 3% capture that read as internally consistent and passed review. Here nobody
 * types a date. The operator presses Start when the instrument starts and Stop
 * when it stops, and the phone records the moment. The same applies to the
 * coordinates, which the phone reads rather than the operator recalls.
 *
 * It deliberately adds nothing to the backend. A visit is an ordinary campaign
 * created through the endpoints the office already uses, so nothing new can
 * break the report path and deleting this file plus its two lines in App.js
 * removes the feature completely.
 *
 * What it is not: a full offline application. An in-progress visit survives a
 * locked phone, a flat battery and a closed tab, because it is written to the
 * device as it is filled in and the campaign is created on the server at the
 * moment Start is pressed. But the network calls themselves need a connection.
 * A failed send says so, keeps everything, and offers to try again — the one
 * outcome that must never happen is an operator believing a visit was recorded
 * when it was not.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight, Camera, Check, ChevronLeft, Droplets, Images, Loader2, MapPin,
  Moon, Mountain, Sun, Trash2,
} from "lucide-react";
import {
  createCampaign, createSiteSample, listCampaigns, listOperators,
  listStations, updateCampaign, uploadAttachments,
} from "@/lib/api";
import FieldCamera, { DATE_FORMATS, cardinal } from "@/components/FieldCamera";

const DRAFT_KEY = "bsa.field.visits";
const THEME_KEY = "bsa.field.theme";
const DATEFMT_KEY = "bsa.field.datefmt";
const OPERATOR_KEY = "bsa.field.operator";

function uid() {
  try { return crypto.randomUUID(); }
  catch { return `v-${Date.now()}-${Math.random().toString(16).slice(2)}`; }
}

// Four fixed views, so the same record is made at every site and nothing is
// left out because the operator was in a hurry. The compass writes the bearing
// he actually faced, which is why the label and the reading are kept apart.
const VIEWS = ["Station", "North", "East", "South"];

/** A local wall-clock stamp in the form the campaign form itself uses.
 *  Deliberately not ISO/UTC: every timestamp in this system is naive local
 *  (KSA), and handing the server a UTC instant here would shift the window by
 *  three hours — the same class of error this page exists to prevent. */
function localStamp(d = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
    + `T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function words(stamp) {
  if (!stamp) return "—";
  const d = new Date(stamp);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function elapsed(fromStamp) {
  const a = new Date(fromStamp).getTime();
  if (Number.isNaN(a)) return "00:00:00";
  const s = Math.max(0, Math.floor((Date.now() - a) / 1000));
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
}

const STEPS = ["Site", "Position", "Photographs", "Samples", "Start",
  "Running", "Done"];

const BLANK = {
  step: 0,
  id: "",
  visitId: "",
  types: ["air"],          // air, noise, or both — both makes two campaigns
  campaignIds: {},         // { air: id, noise: id }
  project_name: "",
  client: "",
  site_name: "",
  latitude: "",
  longitude: "",
  accuracy: null,
  station_id: "",
  inlet_height: "3",
  site_conditions: "",
  met_wind_speed: "",
  met_wind_dir: "",
  monitoring_start: "",
  monitoring_end: "",
};

function blankVisit() {
  return { ...BLANK, id: uid(), visitId: uid() };
}

export default function FieldCapture() {
  const navigate = useNavigate();
  // Several surveys can be open at once: a site is set up, the next is set up
  // an hour later, and both run for a day. So a visit is one of a list, and
  // the page opens on that list rather than on an empty form.
  const [visits, setVisits] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [operator, setOperator] = useState(
    () => localStorage.getItem(OPERATOR_KEY) || "");
  const v = visits.find((x) => x.id === activeId) || BLANK;
  const setV = useCallback((updater) => {
    setVisits((all) => all.map((x) => (x.id === activeId
      ? (typeof updater === "function" ? updater(x) : { ...x, ...updater })
      : x)));
  }, [activeId]);
  const [busy, setBusy] = useState(false);
  // Kept outside the saved visit: a File cannot be written to local storage,
  // so anything not yet sent lives only while the page is open. Keyed by visit
  // so two open surveys cannot mix their photographs.
  const [media, setMedia] = useState({});
  const photos = media[activeId]?.photos || [];
  const samples = media[activeId]?.samples || [];
  const setPhotos = useCallback((updater) => {
    setMedia((m) => {
      const cur = m[activeId] || { photos: [], samples: [] };
      return { ...m, [activeId]: { ...cur,
        photos: typeof updater === "function" ? updater(cur.photos) : updater } };
    });
  }, [activeId]);
  const setSamples = useCallback((updater) => {
    setMedia((m) => {
      const cur = m[activeId] || { photos: [], samples: [] };
      return { ...m, [activeId]: { ...cur,
        samples: typeof updater === "function" ? updater(cur.samples) : updater } };
    });
  }, [activeId]);
  const [operators, setOperators] = useState([]);
  const sampleCamRef = useRef(null);
  const sampleGalRef = useRef(null);
  const [stations, setStations] = useState([]);
  const [known, setKnown] = useState({ projects: [], clients: [] });
  const [locating, setLocating] = useState(false);
  const [tick, setTick] = useState(0);
  const fileRef = useRef(null);
  const [camFor, setCamFor] = useState(null);  // { view, survey }
  const [dateFmt, setDateFmt] = useState(
    () => localStorage.getItem(DATEFMT_KEY) || "long");
  useEffect(() => { localStorage.setItem(DATEFMT_KEY, dateFmt); }, [dateFmt]);

  // While the field page is open it behaves like an application rather than a
  // web page: no pinch-zoom, no double-tap zoom, no rubber-band scroll past
  // the edges. All of it is undone on the way out — done globally in
  // index.html it would also take pinch-zoom away from the office pages,
  // where enlarging a results table on a phone is sometimes the only way to
  // read a figure.
  useEffect(() => {
    const meta = document.querySelector('meta[name="viewport"]');
    const before = meta ? meta.getAttribute("content") : null;
    if (meta) {
      meta.setAttribute(
        "content",
        "width=device-width, initial-scale=1, maximum-scale=1, "
        + "user-scalable=no, viewport-fit=cover",
      );
    }
    const html = document.documentElement;
    const body = document.body;
    const prevOverscroll = body.style.overscrollBehavior;
    const prevTouch = body.style.touchAction;
    const prevSelect = body.style.userSelect;
    body.style.overscrollBehavior = "none";
    body.style.touchAction = "manipulation";   // kills the double-tap zoom
    body.style.userSelect = "none";            // long-press selects nothing
    html.classList.add("bsa-field");

    // Safari on iOS ignores user-scalable, so a two-finger gesture has to be
    // refused outright. Single-finger scrolling is untouched.
    const noPinch = (e) => { if (e.touches && e.touches.length > 1) e.preventDefault(); };
    document.addEventListener("touchmove", noPinch, { passive: false });
    document.addEventListener("gesturestart", noPinch, { passive: false });

    return () => {
      if (meta && before) meta.setAttribute("content", before);
      body.style.overscrollBehavior = prevOverscroll;
      body.style.touchAction = prevTouch;
      body.style.userSelect = prevSelect;
      html.classList.remove("bsa-field");
      document.removeEventListener("touchmove", noPinch);
      document.removeEventListener("gesturestart", noPinch);
    };
  }, []);

  // A short buzz on the two moments that cannot be undone. Confirmation
  // without looking, which matters wearing gloves in the sun.
  const buzz = (ms) => { try { navigator.vibrate?.(ms); } catch { /* ignore */ } };

  // Dark by default, and dark after sunset regardless: this is read outdoors
  // in glare, and a white screen at a site at 42 °C is not readable.
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) return saved === "dark";
    const h = new Date().getHours();
    return h >= 17 || h < 6;
  });
  useEffect(() => {
    localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  }, [dark]);

  // ---- an in-progress visit outlives the page -----------------------------
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      const list = raw ? JSON.parse(raw) : null;
      if (Array.isArray(list)) setVisits(list);
    } catch { /* a corrupt store is not worth failing over */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(visits)); }
    catch { /* full */ }
  }, [visits]);
  useEffect(() => {
    if (operator) localStorage.setItem(OPERATOR_KEY, operator);
  }, [operator]);

  // ---- lists the operator picks from, rather than typing ------------------
  useEffect(() => {
    (async () => {
      try {
        const cs = await listCampaigns();
        setKnown({
          projects: [...new Set(cs.map((c) => c.project_name).filter(Boolean))],
          clients: [...new Set(cs.map((c) => c.client).filter(Boolean))],
        });
      } catch { /* offline: the fields still accept typing */ }
      try { setOperators(await listOperators()); } catch { setOperators([]); }
    })();
  }, []);
  useEffect(() => {
    (async () => {
      try {
        setStations(await listStations(
          v.types.length === 1 && v.types[0] === "noise" ? "noise" : "air"));
      } catch { setStations([]); }
    })();
  }, [v.types]);

  // the running clock
  useEffect(() => {
    if (!visits.some((x) => x.step === 5)) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [visits]);

  // Steps 4 and 5 are after Start: the survey exists on the server and its
  // time is fixed, so going back to edit the form would be a lie about what
  // was recorded. Back is simply not offered there.
  // Before Start, back walks the steps. From the first step, or once a survey
  // is running, it returns to the list and leaves the survey running — it must
  // never look like a way to undo a survey that has already begun.
  const canGoBack = activeId != null;
  const back = useCallback(() => {
    const cur = visits.find((x) => x.id === activeId);
    if (cur && cur.step > 0 && cur.step < 5) {
      setV((s) => ({ ...s, step: s.step - 1 }));
    } else {
      setActiveId(null);
    }
  }, [visits, activeId, setV]);

  // The phone's own back gesture moves a step rather than leaving the app.
  // Without this, one swipe from step 3 closes a half-filled visit.
  useEffect(() => {
    if (!canGoBack) return undefined;
    window.history.pushState({ fieldStep: v.step }, "");
    const onPop = () => setV((s) => ({ ...s, step: Math.max(0, s.step - 1) }));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [v.step, canGoBack, setV]);

  const set = (k) => (e) =>
    setV((s) => ({ ...s, [k]: e?.target ? e.target.value : e }));
  const go = (step) => setV((s) => ({ ...s, step }));

  // ---- the phone's own reading -------------------------------------------
  const readPosition = useCallback(() => new Promise((resolve) => {
    if (!navigator.geolocation) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        latitude: pos.coords.latitude.toFixed(6),
        longitude: pos.coords.longitude.toFixed(6),
        // Kept and shown. A coordinate without its accuracy is a guess wearing
        // a suit, and between buildings a phone can be 40 m out.
        accuracy: Math.round(pos.coords.accuracy),
      }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }), []);

  const locate = useCallback(async () => {
    setLocating(true);
    const p = await readPosition();
    setLocating(false);
    if (!p) {
      toast.error("Could not get a position — enter it by hand if needed");
      return;
    }
    setV((s) => ({ ...s, ...p }));
  }, [readPosition, setV]);
  useEffect(() => { if (v.step === 1 && !v.latitude) locate(); }, [v.step]); // eslint-disable-line react-hooks/exhaustive-deps

  const addSample = async (kind, file) => {
    // Its own position, not the station's: a sample is often taken some way
    // from the instrument, and that distance is the whole point of recording
    // where it came from.
    const p = await readPosition();
    setSamples((all) => [...all, {
      kind, file: file || null, at: localStamp(),
      lat: p?.latitude || v.latitude, lon: p?.longitude || v.longitude,
      acc: p?.accuracy ?? v.accuracy,
    }]);
    buzz(18);
  };
  const countOf = (kind) => samples.filter((s) => s.kind === kind).length;

  /** Adds a sample by count rather than by capturing it.
   *
   *  Kept separate from the one-at-a-time button on purpose. A sample added
   *  individually carries its own position and the moment it was taken; one
   *  added by count carries the site's position and the time it was typed,
   *  which is not the same claim. The record says which it was, so nobody
   *  later reads a site coordinate as the place a sample came from. */
  const addByCount = (kind) => {
    setSamples((all) => [...all, {
      kind, file: null, at: localStamp(),
      lat: v.latitude, lon: v.longitude, acc: v.accuracy,
      byCount: true,
    }]);
    buzz(12);
  };

  const removeLastByCount = (kind) => {
    setSamples((all) => {
      for (let i = all.length - 1; i >= 0; i -= 1) {
        if (all[i].kind === kind && all[i].byCount) {
          return all.filter((_, j) => j !== i);
        }
      }
      // Nothing typed to remove: a captured sample is never taken away by the
      // minus button, only by its own delete.
      toast.error("Only counted samples can be removed here");
      return all;
    });
  };

  // ---- Start: the campaign is created here, at the instrument ------------
  const start = async () => {
    if (!operator) { toast.error("Choose who is recording this"); go(0); return; }
    if (!v.project_name.trim() || !v.client.trim()) {
      toast.error("Project and client are needed first"); go(0); return;
    }
    if (!v.types.length) { toast.error("Choose air, noise, or both"); go(0); return; }
    // The campaign cannot exist without coordinates, so this is caught here
    // rather than failing after Start has been pressed at the instrument.
    if (!v.latitude || !v.longitude) {
      toast.error("A position is needed — read it, or type it in"); go(1); return;
    }

    setBusy(true);
    const started = localStamp();
    const made = {};
    try {
      for (const type of v.types) {
        const c = await createCampaign({
          project_name: v.project_name.trim(),
          client: v.client.trim(),
          site_name: v.site_name.trim() || v.project_name.trim(),
          campaign_type: type,
          latitude: Number(v.latitude),
          longitude: Number(v.longitude),
          inlet_height_m: v.inlet_height ? Number(v.inlet_height) : 5.0,
          monitoring_start: started,
          // The model requires an end, and the survey has not finished. It is
          // set equal to the start rather than guessed at start + 24 h: a
          // zero-length window is obviously unfinished and the campaign form
          // refuses to save it, whereas a guessed end would look like a real
          // one and could reach a report. Stop replaces it with the true time.
          monitoring_end: started,
          site_conditions_note: v.site_conditions || null,
          met_wind_mean_ms: v.met_wind_speed ? Number(v.met_wind_speed) : null,
          met_wind_prevailing: v.met_wind_dir || null,
          prepared_by: operator,
        });
        made[type] = c.id;
        // station_id is not part of the creation model, so it follows as an
        // update rather than being dropped silently.
        if (v.station_id) {
          try { await updateCampaign(c.id, { station_id: v.station_id }); }
          catch { /* set it at home */ }
        }
      }
      setV((s) => ({ ...s, step: 5, campaignIds: made, monitoring_start: started }));
      buzz([28, 40, 28]);
      toast.success(v.types.length > 1 ? "Two campaigns started" : "Survey started");
      sendPhotos(made);
    } catch {
      toast.error("Could not start — nothing was lost, try again when you have signal");
    } finally {
      setBusy(false);
    }
  };

  /** Photographs go to the campaign they belong to, as ordinary attachments of
   *  kind "site_photo" — so they appear on that campaign's Attachments tab
   *  with everything else, and there is no separate field album to hunt in.
   *  The caption carries the view and the bearing, so the record survives the
   *  file being renamed. Whatever fails to send stays on the phone. */
  const sendPhotos = async (ids) => {
    const map = ids || v.campaignIds;
    const pending = photos.filter((p) => map[p.survey]);
    if (!pending.length) return;
    const sent = [];
    try {
      for (const p of pending) {
        const bits = [p.view, p.heading == null ? null
          : `facing ${String(p.heading).padStart(3, "0")}° ${cardinal(p.heading)}`];
        await uploadAttachments(map[p.survey], "site_photo", [p.file],
          { caption: bits.filter(Boolean).join(" · ") });
        sent.push(p);
      }
    } catch {
      toast.error("Some photographs are still on the phone");
    } finally {
      setPhotos((all) => all.filter((p) => !sent.includes(p)));
    }
  };

  /** Samples are sent at the end rather than as they are taken: at a site
   *  there is often no signal, and a failed send mid-visit would leave the
   *  operator unsure which had gone. They go together, and whatever fails
   *  stays. They belong to the visit, not to either campaign — which is why
   *  they carry the visit's own identifier and nothing else. */
  const sendSamples = async () => {
    if (!samples.length) return;
    const sent = [];
    try {
      for (const s of samples) {
        await createSiteSample({
          visit_id: v.visitId,
          kind: s.kind,
          project_name: v.project_name,
          client: v.client,
          site_name: v.site_name,
          latitude: s.lat || undefined,
          longitude: s.lon || undefined,
          accuracy_m: s.acc || undefined,
          taken_at: s.at,
          recorded_by: operator,
          // So the office can tell the two apart. A counted sample's position
          // is the site's, not the sample's, and saying so is the difference
          // between a record and a guess.
          note: s.byCount ? "Counted on site — position is the station's" : undefined,
        }, s.file || undefined);
        sent.push(s);
      }
    } catch {
      toast.error("Some samples are still on the phone");
    } finally {
      setSamples((all) => all.filter((s) => !sent.includes(s)));
    }
  };

  // ---- Stop --------------------------------------------------------------
  const stop = async () => {
    setBusy(true);
    const ended = localStamp();
    try {
      for (const id of Object.values(v.campaignIds)) {
        await updateCampaign(id, { monitoring_end: ended });
      }
      await sendPhotos();
      await sendSamples();
      setV((s) => ({ ...s, step: 6, monitoring_end: ended }));
      buzz([40, 60, 90]);
      toast.success("Survey closed");
    } catch {
      toast.error("Could not close it — the start time is safe, try again");
    } finally {
      setBusy(false);
    }
  };

  /** A new visit joins the list and becomes the open one. */
  const newVisit = () => {
    const fresh = blankVisit();
    setVisits((all) => [...all, fresh]);
    setActiveId(fresh.id);
  };

  /** Takes a finished visit off the phone. The campaigns and anything already
   *  sent stay where they are; only the local copy goes. */
  const closeVisit = (id) => {
    setVisits((all) => all.filter((x) => x.id !== id));
    setMedia((m) => { const n = { ...m }; delete n[id]; return n; });
    setActiveId((cur) => (cur === id ? null : cur));
  };

  // ---- appearance ---------------------------------------------------------
  const T = dark
    ? {
      shell: "bg-[#0a1420] text-[#eef3f8]",
      sub: "text-[#8fa3b8]", faint: "text-[#63788d]",
      ctl: "border-white/10 bg-white/[0.035]",
      sensed: "border-emerald-400/30 bg-emerald-400/10",
      card: "border-white/10",
      rail: "bg-white/10", railOn: "bg-emerald-300",
    }
    : {
      shell: "bg-[#f6f8fa] text-slate-900",
      sub: "text-slate-500", faint: "text-slate-400",
      ctl: "border-slate-200 bg-white",
      sensed: "border-emerald-300 bg-emerald-50",
      card: "border-slate-200",
      rail: "bg-slate-200", railOn: "bg-emerald-500",
    };

  const Label = ({ children }) => (
    <span className={`block text-[9.5px] uppercase tracking-[.13em] mb-1.5 ${T.faint}`}>
      {children}
    </span>
  );
  const Ctl = ({ children, sensed }) => (
    <div className={`rounded-xl border px-3.5 py-2.5 text-[14px]
      ${sensed ? T.sensed : T.ctl}`}>{children}</div>
  );
  // Which surveys this visit covers, and the shared class for a text input.
  // Both were used throughout the screens below but never declared — a patch
  // that did not apply, shipped without checking, which blanked the page.
  const surveys = v.types;
  const field = `w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`;
  // A native select's option list is drawn by the operating system, not by the
  // page, so every class on the element is ignored and the names came out
  // near-invisible in dark mode. colorScheme is the one thing the browser does
  // listen to; the explicit option colours are for the Android builds that
  // keep a white list regardless.
  const selectStyle = { colorScheme: dark ? "dark" : "light" };
  const optionStyle = dark
    ? { backgroundColor: "#101d2d", color: "#eef3f8" }
    : { backgroundColor: "#ffffff", color: "#0f172a" };

  const Btn = ({ children, onClick, tone = "solid", disabled }) => {
    const tones = {
      solid: "bg-gradient-to-b from-emerald-300 to-emerald-500 text-[#06121c] font-semibold",
      dark: dark
        ? "bg-white/[0.06] border border-white/10 text-[#eef3f8] font-semibold"
        : "bg-slate-900 text-white font-semibold",
      stop: "bg-gradient-to-b from-rose-400 to-rose-600 text-white font-semibold",
      quiet: `border ${dark ? "border-white/10" : "border-slate-200"} ${T.sub}`,
    };
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={disabled || busy}
        className={`w-full rounded-2xl px-4 py-4 text-[15px] mt-3.5
          disabled:opacity-60 active:scale-[.99] transition ${tones[tone]}`}
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : children}
      </button>
    );
  };

  return (
    // colorScheme is set on the whole page, not on each control: the project
    // and client suggestion lists, the file picker and the scrollbars are all
    // drawn by the operating system too, and they were all going to be as
    // unreadable in dark mode as the name list was.
    <div className={`min-h-screen ${T.shell}`}
      style={{ colorScheme: dark ? "dark" : "light" }}>
      {/* The padding follows the phone's safe areas so nothing sits under the
          notch or the home indicator when this runs full-screen from the home
          screen, and falls back to plain padding in a browser tab. */}
      <div
        className="mx-auto w-full max-w-[430px] px-5"
        style={{
          paddingTop: "calc(env(safe-area-inset-top, 0px) + 14px)",
          paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 40px)",
        }}
      >
        {/* One back control, in the same place on every screen, sized for a
            thumb. In a home-screen app there is no browser back button, so
            this is the only way out of a step — the small text links that were
            at the foot of some screens and absent from others were neither
            findable nor reachable one-handed. */}
        <div className="flex items-center gap-2.5">
          {canGoBack && (
            <button
              type="button"
              onClick={back}
              aria-label="Back"
              className={`-ml-2 mr-0.5 grid h-10 w-10 place-items-center rounded-xl
                border active:scale-95 transition
                ${dark ? "border-white/10 bg-white/[0.04]" : "border-slate-200 bg-white"}`}
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
          )}
          {/* Two files rather than a CSS filter: inverting the mark would
              turn the leaf white as well, and the leaf is the half of it
              anyone recognises. The light variant lifts only the wordmark. */}
          <img
            src={dark ? "/logo-mark-light.png" : "/logo-mark.png"}
            alt="BSA.lab"
            className="h-7 w-auto"
          />
          <span className={`text-[10px] uppercase tracking-[.14em] ml-auto ${T.faint}`}>
            Field
          </span>
          <button
            type="button"
            onClick={() => setDark((d) => !d)}
            aria-label={dark ? "Switch to day" : "Switch to night"}
            className={`ml-1 rounded-lg border p-1.5 ${dark ? "border-white/10" : "border-slate-200"}`}
          >
            {dark ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          </button>
        </div>

        <div className="flex gap-1.5 mt-4 mb-5">
          {STEPS.map((s, i) => (
            <i key={s} className={`h-[3px] flex-1 rounded-full
              ${i === v.step ? T.railOn : i < v.step ? "bg-emerald-500/50" : T.rail}`} />
          ))}
        </div>

        {/* The list of open visits. Several can run at once — a site is set
            up, the next an hour later, both running for a day — so the app
            opens here, and a running survey is never more than one tap away. */}
        {activeId == null && (
          <section>
            <h1 className="text-[21px] font-semibold tracking-tight">
              {operator ? `Hello, ${operator.split(" ")[0]}` : "Site visits"}
            </h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              {visits.length
                ? `${visits.filter((x) => x.step === 5).length} running`
                : "Nothing open. Start a visit when you reach the site."}
            </p>

            {visits.map((x) => {
              const running = x.step === 5;
              const done = x.step === 6;
              const m = media[x.id] || { photos: [], samples: [] };
              const waiting = m.photos.length + m.samples.length;
              return (
                <button key={x.id} type="button" onClick={() => setActiveId(x.id)}
                  className={`w-full text-left rounded-xl border px-3.5 py-3 mb-2.5
                    ${running ? "border-amber-400/30 bg-amber-400/10"
                      : done ? T.sensed : T.ctl}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-[14px] font-semibold">
                      {x.site_name || x.project_name || "Untitled visit"}
                    </span>
                    <span className={`ml-auto text-[10px] uppercase tracking-[.12em]
                      ${running ? "text-amber-400"
                        : done ? "text-emerald-400" : T.faint}`}>
                      {running ? "Running" : done ? "Closed" : `Step ${x.step + 1}`}
                    </span>
                  </div>
                  <div className={`text-[11.5px] mt-1 ${T.sub}`}>
                    {running ? (
                      <span className="tabular-nums">
                        {elapsed(x.monitoring_start)} · started{" "}
                        {words(x.monitoring_start)}
                        <span className="hidden">{tick}</span>
                      </span>
                    ) : done ? "Data file still to upload at home"
                      : (x.client || "Not started")}
                  </div>
                  {waiting > 0 && (
                    <div className={`text-[10.5px] mt-1 ${T.faint}`}>
                      {m.photos.length} photograph{m.photos.length === 1 ? "" : "s"}
                      {" · "}{m.samples.length} sample{m.samples.length === 1 ? "" : "s"}
                      {" waiting to send"}
                    </div>
                  )}
                </button>
              );
            })}

            <Btn onClick={newVisit}>Start a new site visit</Btn>
          </section>
        )}

        {/* 0 — what and where */}
        {activeId != null && v.step === 0 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 1 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">New site visit</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Nothing typed that the phone already knows.
            </p>

            <div className="mb-2.5">
              <Label>Recorded by</Label>
              {operators.length ? (
                <select value={operator} style={selectStyle}
                  onChange={(e) => setOperator(e.target.value)}
                  className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`}>
                  <option value="" style={optionStyle}>Choose your name</option>
                  {operators.map((o) => (
                    <option key={o.id} value={o.name} style={optionStyle}>
                      {o.name}
                    </option>
                  ))}
                </select>
              ) : (
                /* Only when the list could not be fetched — offline, or no
                   accounts yet. Choosing from a known set is the point, so
                   this is a fallback and not the normal path. */
                <input value={operator}
                  onChange={(e) => setOperator(e.target.value)}
                  placeholder="Your name"
                  className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`} />
              )}
            </div>

            <div className="mb-2.5">
              <Label>Surveys at this site</Label>
              <div className="grid grid-cols-2 gap-2">
                {[["air", "Air quality"], ["noise", "Noise"]].map(([k, lbl]) => {
                  const on = v.types.includes(k);
                  return (
                    <button key={k} type="button"
                      onClick={() => setV((s) => ({
                        ...s,
                        types: on ? s.types.filter((t) => t !== k) : [...s.types, k],
                        station_id: "",
                      }))}
                      className={`rounded-xl border px-3 py-2.5 text-[13.5px]
                        flex items-center gap-2 ${on ? T.sensed : T.ctl}`}>
                      <span className={`grid h-4 w-4 place-items-center rounded border
                        ${on ? "bg-emerald-400 border-emerald-400" : T.ctl}`}>
                        {on && <Check className="h-3 w-3 text-[#06121c]" />}
                      </span>
                      {lbl}
                    </button>
                  );
                })}
              </div>
              {v.types.length > 1 && (
                <p className={`text-[10.5px] mt-1.5 ${T.faint}`}>
                  Two campaigns, one window. Photographs kept separate.
                </p>
              )}
            </div>

            <div className="mb-2.5">
              <Label>Project</Label>
              <input list="fld-projects" value={v.project_name}
                onChange={set("project_name")} placeholder="Project name"
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`} />
              <datalist id="fld-projects">
                {known.projects.map((p) => <option key={p} value={p} />)}
              </datalist>
            </div>
            <div className="mb-2.5">
              <Label>Client</Label>
              <input list="fld-clients" value={v.client} onChange={set("client")}
                placeholder="Client"
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`} />
              <datalist id="fld-clients">
                {known.clients.map((c) => <option key={c} value={c} />)}
              </datalist>
            </div>
            <div className="mb-2.5">
              <Label>Site</Label>
              <input value={v.site_name} onChange={set("site_name")}
                placeholder="Site name"
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`} />
            </div>
            <Btn tone="dark" onClick={() => go(1)}>
              Continue <ArrowRight className="inline w-4 h-4 ml-1" />
            </Btn>
          </section>
        )}

        {/* 1 — position and equipment */}
        {activeId != null && v.step === 1 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 2 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">Where you are</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>Read from the phone, not entered.</p>

            <div className="mb-2.5">
              <Label>Coordinates</Label>
              <Ctl sensed={!!v.latitude}>
                {locating ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Finding a fix…
                  </span>
                ) : v.latitude ? (
                  <>
                    <span className="font-medium">{v.latitude}, {v.longitude}</span>
                    <span className="block text-[10.5px] text-emerald-400 mt-0.5">
                      Accurate to ±{v.accuracy} m
                      {v.accuracy > 25 && " — poor; move to open sky"}
                    </span>
                  </>
                ) : "No position yet"}
              </Ctl>
              <button type="button" onClick={locate}
                className={`mt-2 text-[11.5px] inline-flex items-center gap-1.5 ${T.sub}`}>
                <MapPin className="w-3.5 h-3.5" /> Read it again
              </button>
            </div>

            <div className="mb-2.5">
              <Label>Equipment</Label>
              <select value={v.station_id} onChange={set("station_id")}
                style={selectStyle}
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`}>
                <option value="" style={optionStyle}>Not selected</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id} style={optionStyle}>
                    {s.name}{s.serial ? ` · ${s.serial}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="mb-2.5">
              <Label>Inlet height (m)</Label>
              <input value={v.inlet_height} onChange={set("inlet_height")}
                inputMode="decimal"
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`} />
            </div>
            <Btn tone="dark" onClick={() => go(2)}>Continue</Btn>
          </section>
        )}

        {/* 2 — photographs and conditions */}
        {activeId != null && v.step === 2 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 3 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">Photographs</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Taken now, sent with the visit.
            </p>

            {surveys.map((survey) => (
              <div key={survey} className="mb-4">
                {surveys.length > 1 && (
                  <Label>{survey === "air" ? "Air quality" : "Noise"}</Label>
                )}
                <div className="grid grid-cols-2 gap-2.5">
                  {VIEWS.map((name) => {
                    const shot = photos.find(
                      (p) => p.view === name && p.survey === survey);
                    return (
                      <button key={name} type="button"
                        onClick={() => setCamFor({ view: name, survey })}
                        className={`rounded-xl border px-3 py-3 text-left
                          ${shot ? T.sensed : T.ctl}`}>
                        <span className="flex items-center gap-2 text-[13.5px] font-medium">
                          {shot ? <Check className="w-4 h-4 text-emerald-400" />
                                : <Camera className="w-4 h-4 opacity-60" />}
                          {name}
                        </span>
                        <span className={`block text-[10.5px] mt-1 ${T.faint}`}>
                          {shot
                            ? (shot.heading == null ? "From gallery"
                              : `${String(shot.heading).padStart(3, "0")}° ${cardinal(shot.heading)}`)
                            : "Not taken"}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <button type="button"
                  onClick={() => setCamFor({ view: "Extra", survey })}
                  className={`mt-2.5 w-full rounded-xl border border-dashed px-3 py-2.5
                    text-[12.5px] ${T.ctl} ${T.sub}`}>
                  Another photograph
                </button>
              </div>
            ))}

            <div className="mt-3">
              <Label>Date shown on the photograph</Label>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(DATE_FORMATS).map(([k, f]) => (
                  <button key={k} type="button" onClick={() => setDateFmt(k)}
                    className={`rounded-xl border px-2 py-2 text-[12px] tabular-nums
                      ${dateFmt === k ? T.sensed : T.ctl}`}>
                    {f.label}
                  </button>
                ))}
              </div>
              <p className={`text-[10.5px] mt-1.5 ${T.faint}`}>
                The time itself is taken from the phone and cannot be changed.
              </p>
            </div>

            <div className="mt-4 mb-2.5">
              <Label>Site conditions</Label>
              <textarea value={v.site_conditions} onChange={set("site_conditions")}
                rows={2} placeholder="Open ground, no obstruction within 20 m"
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`} />
            </div>
            <Btn tone="dark" onClick={() => go(3)}>Continue</Btn>
          </section>
        )}

        {/* 3 — samples */}
        {activeId != null && v.step === 3 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 4 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">Samples taken</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Each keeps its own time and position. Skip if there are none.
            </p>

            {samples.length > 0 && (
              <div className="mb-3 space-y-2">
                {samples.map((sm, i) => {
                  const n = samples.filter((x, j) => x.kind === sm.kind && j <= i).length;
                  const Icon = sm.kind === "water" ? Droplets : Mountain;
                  return (
                    <div key={i} className={`rounded-xl border px-3 py-2.5 ${T.ctl}`}>
                      <div className="flex items-center gap-2">
                        <Icon className={`w-4 h-4 ${sm.kind === "water"
                          ? "text-sky-400" : "text-amber-500"}`} />
                        <span className="text-[13.5px] font-medium capitalize">
                          {sm.kind} {n}
                        </span>
                        <button type="button" aria-label="Remove"
                          onClick={() => setSamples((all) => all.filter((_, j) => j !== i))}
                          className={`ml-auto ${T.faint}`}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <div className={`text-[10.5px] mt-1 ${T.faint}`}>
                        {words(sm.at)}
                        {sm.byCount
                          ? " · counted, site position"
                          : (sm.lat ? ` · ${sm.lat}, ${sm.lon}` : " · no position")}
                        {sm.file ? " · photo" : ""}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {[["water", "Water", Droplets, "text-sky-400"],
              ["soil", "Soil", Mountain, "text-amber-500"]].map(([k, lbl, Icon, tone]) => (
              <div key={k} className={`rounded-xl border px-3.5 py-3 mb-2.5 ${T.ctl}`}>
                <div className="flex items-center gap-2">
                  <Icon className={`w-4 h-4 ${tone}`} />
                  <span className="text-[13.5px] font-medium">{lbl}</span>
                  <span className={`ml-auto text-[11px] ${T.faint}`}>
                    {countOf(k)} recorded
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 mt-2.5">
                  <button type="button"
                    onClick={() => {
                      sampleCamRef.current.dataset.kind = k;
                      sampleCamRef.current.click();
                    }}
                    className={`rounded-xl border px-3 py-2.5 text-[12.5px]
                      flex items-center justify-center gap-1.5 ${T.sensed}`}>
                    <Camera className="w-3.5 h-3.5" /> Camera
                  </button>

                  {/* Photographs already taken — with his own timestamp
                      camera, or before the app was opened. Each picture
                      becomes one sample, so choosing four adds four. */}
                  <button type="button"
                    onClick={() => {
                      sampleGalRef.current.dataset.kind = k;
                      sampleGalRef.current.click();
                    }}
                    className={`rounded-xl border px-3 py-2.5 text-[12.5px]
                      flex items-center justify-center gap-1.5 ${T.ctl}`}>
                    <Images className="w-3.5 h-3.5" /> Gallery
                  </button>
                </div>

                <div className="mt-2">
                  {/* Counting, for samples already taken or when there is no
                      time to photograph each. */}
                  <div className={`rounded-xl border flex items-center
                    ${T.ctl}`}>
                    <button type="button" aria-label={`One fewer ${lbl}`}
                      onClick={() => removeLastByCount(k)}
                      className="flex-1 py-2.5 text-[16px] leading-none">−</button>
                    <span className="text-[13px] tabular-nums w-8 text-center">
                      {samples.filter((x) => x.kind === k && x.byCount).length}
                    </span>
                    <button type="button" aria-label={`One more ${lbl}`}
                      onClick={() => addByCount(k)}
                      className="flex-1 py-2.5 text-[16px] leading-none">+</button>
                  </div>
                </div>
              </div>
            ))}

            <p className={`text-[10.5px] mt-1 ${T.faint}`}>
              <b>Camera</b> and <b>Gallery</b> each add one sample per
              photograph, with a position read now. <b>+</b> just counts: the
              site position and this moment are recorded, and the sample is
              marked as counted. All are sent when you stop, and listed under
              Site Samples.
            </p>

            {/* The phone's own camera here, not the stamped one: a sample
                photograph records the container, not a bearing, and fewer taps
                at this point is worth more than a stamp. */}
            <input ref={sampleCamRef} type="file" accept="image/*"
              capture="environment" className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0] || null;
                const kind = e.target.dataset.kind || "water";
                e.target.value = "";
                addSample(kind, f);
              }} />

            {/* No capture attribute, so the gallery opens rather than the
                camera. Several at once: each picture is its own sample, and
                they all take the position read now — the pictures were taken
                earlier, so their own position is not something we know. */}
            <input ref={sampleGalRef} type="file" accept="image/*" multiple
              className="hidden"
              onChange={async (e) => {
                const files = Array.from(e.target.files || []);
                const kind = e.target.dataset.kind || "water";
                e.target.value = "";
                for (const f of files) {
                  await addSample(kind, f);
                }
              }} />

            <Btn tone="dark" onClick={() => go(4)}>Continue</Btn>
          </section>
        )}

        {/* 4 — weather, then start */}
        {activeId != null && v.step === 4 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 5 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">Begin the survey</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Press as the instrument starts. This is the time the report carries.
            </p>

            {/* Temperature is not asked for. The report states a maximum and
                a minimum across the whole survey; a single reading taken at
                the moment of arrival is neither, and recording it as one
                would be a plausible wrong number. It belongs in the note. */}
            <div className="grid grid-cols-2 gap-2 mb-2.5">
              <div><Label>Wind m/s</Label>
                <input value={v.met_wind_speed} onChange={set("met_wind_speed")} inputMode="decimal"
                  className={`w-full rounded-xl border px-3 py-2.5 text-[14px] outline-none ${T.ctl}`} /></div>
              <div><Label>Dir</Label>
                <input value={v.met_wind_dir} onChange={set("met_wind_dir")} placeholder="E"
                  className={`w-full rounded-xl border px-3 py-2.5 text-[14px] outline-none ${T.ctl}`} /></div>
            </div>

            <div className={`rounded-xl border px-3.5 py-3 ${T.ctl}`}>
              <div className={`text-[10px] uppercase tracking-[.13em] ${T.faint} mb-1.5`}>
                About to create
              </div>
              {surveys.map((t) => (
                <div key={t} className="text-[13px] flex items-center gap-2">
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  {v.project_name || "—"} — {t === "air" ? "Air quality" : "Noise"}
                </div>
              ))}
              <div className={`text-[11px] mt-1.5 ${T.faint}`}>
                {operator || "—"} · {photos.length} photograph{photos.length === 1 ? "" : "s"}
                {" · "}{samples.length} sample{samples.length === 1 ? "" : "s"}
              </div>
            </div>

            <Btn onClick={start}>Start now</Btn>
            <p className={`text-[11px] mt-3 text-center ${T.faint}`}>
              The moment is recorded on the server, not on this phone.
            </p>
          </section>
        )}

        {/* 5 — running */}
        {activeId != null && v.step === 5 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-amber-400 mb-1.5">
              In progress
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">Survey running</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Close the phone. It keeps running.
            </p>

            <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 p-5 text-center">
              <p className="text-[9.5px] uppercase tracking-[.14em] text-amber-400">Elapsed</p>
              <p className="text-[36px] font-semibold tracking-tight tabular-nums my-1">
                {elapsed(v.monitoring_start)}
                <span className="hidden">{tick}</span>
              </p>
              <p className={`text-[11.5px] ${T.sub}`}>Started {words(v.monitoring_start)}</p>
            </div>

            <div className={`rounded-xl border px-3.5 py-2.5 mt-3 ${T.ctl}`}>
              {[["Campaigns", Object.keys(v.campaignIds).length],
                ["Photographs waiting", photos.length],
                ["Samples waiting", samples.length]].map(([k, n]) => (
                <div key={k} className="flex justify-between text-[12.5px] py-1">
                  <span className={T.sub}>{k}</span><b>{n}</b>
                </div>
              ))}
            </div>

            <Btn tone="quiet" onClick={() => go(3)}>Add a sample</Btn>
            <Btn tone="quiet" onClick={() => setActiveId(null)}>
              Leave it running — start another site
            </Btn>
            <Btn tone="stop" onClick={stop}>Stop survey</Btn>
          </section>
        )}

        {/* 6 — done */}
        {activeId != null && v.step === 6 && (
          <section>
            <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-full
              border border-emerald-400/40 bg-emerald-400/10 text-emerald-300">
              <Check className="w-6 h-6" />
            </div>
            <h1 className="text-[21px] font-semibold tracking-tight text-center">
              Visit recorded
            </h1>
            <p className={`text-[12.5px] mb-4 text-center ${T.sub}`}>
              Nothing further to do here.
            </p>

            <div className="mb-2.5">
              <Label>Monitoring window</Label>
              <Ctl sensed>
                <span className="font-medium">
                  {words(v.monitoring_start)} → {words(v.monitoring_end)}
                </span>
                <span className="block text-[10.5px] text-emerald-400 mt-0.5">
                  Both times taken from the phone
                </span>
              </Ctl>
            </div>
            <div className="mb-2.5">
              <Label>Created</Label>
              <Ctl>
                {Object.keys(v.campaignIds).map((t) => (
                  <div key={t} className="text-[13px]">
                    {v.project_name} — {t === "air" ? "Air quality" : "Noise"}
                  </div>
                ))}
              </Ctl>
            </div>
            <div className="mb-2.5">
              <Label>Still needed at home</Label>
              <Ctl>The instrument&rsquo;s data file</Ctl>
            </div>

            <Btn tone="dark" onClick={() => {
              const id = Object.values(v.campaignIds)[0];
              closeVisit(v.id);
              navigate(id ? `/campaigns/${id}` : "/campaigns");
            }}>
              Open the campaign
            </Btn>
            <Btn tone="quiet" onClick={() => closeVisit(v.id)}>Done with this one</Btn>
          </section>
        )}
      </div>

      <FieldCamera
        open={!!camFor}
        view={camFor?.view}
        site={[v.site_name || v.project_name,
          surveys.length > 1
            ? (camFor?.survey === "air" ? "Air" : "Noise") : null]
          .filter(Boolean).join(" · ")}
        coords={{ latitude: v.latitude, longitude: v.longitude, accuracy: v.accuracy }}
        dateFormat={dateFmt}
        onClose={() => setCamFor(null)}
        onCapture={(file, meta) => {
          const survey = camFor?.survey;
          setPhotos((p) => [
            // one photograph per view per survey: taking it again replaces it
            ...p.filter((x) => !(x.view === meta.view && x.survey === survey)
              || meta.view === "Extra"),
            { file, view: meta.view, heading: meta.heading, survey },
          ]);
        }}
      />
    </div>
  );
}
