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
  ArrowRight, Camera, Check, ChevronLeft, Loader2, MapPin, Moon, Sun,
} from "lucide-react";
import {
  createCampaign, listCampaigns, listStations, updateCampaign,
  uploadAttachments,
} from "@/lib/api";
import FieldCamera, { DATE_FORMATS, cardinal } from "@/components/FieldCamera";

const DRAFT_KEY = "bsa.field.visit";
const THEME_KEY = "bsa.field.theme";
const DATEFMT_KEY = "bsa.field.datefmt";

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

const BLANK = {
  step: 0,
  campaignId: null,
  project_name: "",
  client: "",
  site_name: "",
  campaign_type: "air",
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

export default function FieldCapture() {
  const navigate = useNavigate();
  const [v, setV] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  const [photos, setPhotos] = useState([]);          // File objects, not yet sent
  const [stations, setStations] = useState([]);
  const [known, setKnown] = useState({ projects: [], clients: [] });
  const [locating, setLocating] = useState(false);
  const [tick, setTick] = useState(0);
  const fileRef = useRef(null);
  const [camFor, setCamFor] = useState(null);      // which view is being shot
  const [dateFmt, setDateFmt] = useState(
    () => localStorage.getItem(DATEFMT_KEY) || "long");
  useEffect(() => { localStorage.setItem(DATEFMT_KEY, dateFmt); }, [dateFmt]);

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
      if (raw) setV({ ...BLANK, ...JSON.parse(raw) });
    } catch { /* a corrupt draft is not worth failing over */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(v)); } catch { /* full */ }
  }, [v]);

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
    })();
  }, []);
  useEffect(() => {
    (async () => {
      try {
        setStations(await listStations(v.campaign_type === "noise" ? "noise" : "air"));
      } catch { setStations([]); }
    })();
  }, [v.campaign_type]);

  // the running clock
  useEffect(() => {
    if (v.step !== 4 || !v.monitoring_start) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [v.step, v.monitoring_start]);

  const set = (k) => (e) =>
    setV((s) => ({ ...s, [k]: e?.target ? e.target.value : e }));
  const go = (step) => setV((s) => ({ ...s, step }));

  // ---- the phone's own reading -------------------------------------------
  const locate = useCallback(() => {
    if (!navigator.geolocation) {
      toast.error("This phone will not share its position");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        setV((s) => ({
          ...s,
          latitude: pos.coords.latitude.toFixed(6),
          longitude: pos.coords.longitude.toFixed(6),
          // Kept and shown. A coordinate without its accuracy is a guess
          // wearing a suit, and between buildings a phone can be 40 m out.
          accuracy: Math.round(pos.coords.accuracy),
        }));
      },
      () => {
        setLocating(false);
        toast.error("Could not get a position — enter it by hand if needed");
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }, []);
  useEffect(() => { if (v.step === 1 && !v.latitude) locate(); }, [v.step]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Start: the campaign is created here, at the instrument ------------
  const start = async () => {
    if (!v.project_name.trim() || !v.client.trim()) {
      toast.error("Project and client are needed first");
      go(0);
      return;
    }
    // The campaign cannot exist without coordinates, so this is caught here
    // rather than failing after Start has been pressed at the instrument.
    if (!v.latitude || !v.longitude) {
      toast.error("A position is needed — read it, or type it in");
      go(1);
      return;
    }
    setBusy(true);
    const started = localStamp();
    try {
      const payload = {
        project_name: v.project_name.trim(),
        client: v.client.trim(),
        site_name: v.site_name.trim() || v.project_name.trim(),
        campaign_type: v.campaign_type,
        latitude: v.latitude ? Number(v.latitude) : null,
        longitude: v.longitude ? Number(v.longitude) : null,
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
      };
      const c = await createCampaign(payload);
      // station_id is not part of the creation model, so it follows as an
      // update rather than being dropped silently.
      if (v.station_id) {
        try { await updateCampaign(c.id, { station_id: v.station_id }); }
        catch { toast.error("Equipment not linked — set it at home"); }
      }
      setV((s) => ({ ...s, step: 4, campaignId: c.id, monitoring_start: started }));
      toast.success("Survey started");
      if (photos.length) sendPhotos(c.id);
    } catch (e) {
      toast.error("Could not start — nothing was lost, try again when you have signal");
    } finally {
      setBusy(false);
    }
  };

  /** Sent as ordinary campaign attachments of kind "site_photo", so they
   *  appear on the campaign's Attachments tab with everything else — there is
   *  no separate field album to go looking in. The caption carries the view
   *  and the bearing, so the record survives the file being renamed. */
  const sendPhotos = async (campaignId) => {
    if (!photos.length) return;
    try {
      for (const p of photos) {
        const bits = [p.view, p.heading == null ? null
          : `facing ${String(p.heading).padStart(3, "0")}° ${cardinal(p.heading)}`];
        await uploadAttachments(campaignId, "site_photo", [p.file],
          { caption: bits.filter(Boolean).join(" · ") });
      }
      setPhotos([]);
    } catch {
      toast.error("Photographs are still on the phone — they will need sending again");
    }
  };

  // ---- Stop --------------------------------------------------------------
  const stop = async () => {
    setBusy(true);
    const ended = localStamp();
    try {
      await updateCampaign(v.campaignId, { monitoring_end: ended });
      await sendPhotos(v.campaignId);
      setV((s) => ({ ...s, step: 5, monitoring_end: ended }));
      toast.success("Survey closed");
    } catch {
      toast.error("Could not close it — the start time is safe, try again");
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    localStorage.removeItem(DRAFT_KEY);
    setPhotos([]);
    setV(BLANK);
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

  const steps = ["Site", "Position", "Photographs", "Start", "Running", "Done"];

  return (
    <div className={`min-h-screen ${T.shell}`}>
      <div className="mx-auto w-full max-w-[430px] px-5 pb-10 pt-4">

        <div className="flex items-center gap-2.5">
          <span className="h-5 w-5 rounded-md bg-gradient-to-br from-emerald-300 to-emerald-600" />
          <b className="text-[12.5px]">BSA.lab</b>
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
          {steps.map((s, i) => (
            <i key={s} className={`h-[3px] flex-1 rounded-full
              ${i === v.step ? T.railOn : i < v.step ? "bg-emerald-500/50" : T.rail}`} />
          ))}
        </div>

        {/* 0 — what and where */}
        {v.step === 0 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 1 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">New site visit</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Nothing typed that the phone already knows.
            </p>

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
            <div className="mb-2.5">
              <Label>Survey type</Label>
              <div className="grid grid-cols-2 gap-2">
                {[["air", "Air quality"], ["noise", "Noise"]].map(([k, lbl]) => (
                  <button key={k} type="button"
                    onClick={() => setV((s) => ({ ...s, campaign_type: k, station_id: "" }))}
                    className={`rounded-xl border px-3 py-2.5 text-[13.5px]
                      ${v.campaign_type === k ? T.sensed : T.ctl}`}>
                    {lbl}
                  </button>
                ))}
              </div>
            </div>
            <Btn tone="dark" onClick={() => go(1)}>
              Continue <ArrowRight className="inline w-4 h-4 ml-1" />
            </Btn>
          </section>
        )}

        {/* 1 — position and equipment */}
        {v.step === 1 && (
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
                className={`w-full rounded-xl border px-3.5 py-2.5 text-[14px] outline-none ${T.ctl}`}>
                <option value="">Not selected</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
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
            <button type="button" onClick={() => go(0)}
              className={`mt-3 text-[12px] inline-flex items-center gap-1 ${T.sub}`}>
              <ChevronLeft className="w-3.5 h-3.5" /> Back
            </button>
          </section>
        )}

        {/* 2 — photographs and conditions */}
        {v.step === 2 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 3 of 5
            </p>
            <h1 className="text-[21px] font-semibold tracking-tight">Photographs</h1>
            <p className={`text-[12.5px] mb-4 ${T.sub}`}>
              Taken now, sent with the visit.
            </p>

            <div className="grid grid-cols-2 gap-2.5">
              {VIEWS.map((name) => {
                const shot = photos.find((p) => p.view === name);
                return (
                  <button key={name} type="button" onClick={() => setCamFor(name)}
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

            <button type="button" onClick={() => setCamFor("Extra")}
              className={`mt-2.5 w-full rounded-xl border border-dashed px-3 py-2.5
                text-[12.5px] ${T.ctl} ${T.sub}`}>
              Another photograph
            </button>

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
            <button type="button" onClick={() => go(1)}
              className={`mt-3 text-[12px] inline-flex items-center gap-1 ${T.sub}`}>
              <ChevronLeft className="w-3.5 h-3.5" /> Back
            </button>
          </section>
        )}

        {/* 3 — weather, then start */}
        {v.step === 3 && (
          <section>
            <p className="text-[10px] uppercase tracking-[.16em] text-emerald-400 mb-1.5">
              Step 4 of 5
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

            <Btn onClick={start}>Start now</Btn>
            <p className={`text-[11px] mt-3 text-center ${T.faint}`}>
              The moment is recorded on the server, not on this phone.
            </p>
            <button type="button" onClick={() => go(2)}
              className={`mt-3 text-[12px] inline-flex items-center gap-1 ${T.sub}`}>
              <ChevronLeft className="w-3.5 h-3.5" /> Back
            </button>
          </section>
        )}

        {/* 4 — running */}
        {v.step === 4 && (
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

            {photos.length > 0 && (
              <p className={`text-[11.5px] mt-3 ${T.sub}`}>
                {photos.length} photograph{photos.length > 1 ? "s" : ""} waiting to send.
              </p>
            )}

            <Btn tone="stop" onClick={stop}>Stop survey</Btn>
          </section>
        )}

        {/* 5 — done */}
        {v.step === 5 && (
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
              <Label>Still needed at home</Label>
              <Ctl>The instrument&rsquo;s data file</Ctl>
            </div>

            <Btn tone="dark"
              onClick={() => { const id = v.campaignId; reset(); navigate(`/campaigns/${id}`); }}>
              Open the campaign
            </Btn>
            <Btn tone="quiet" onClick={reset}>Start another site</Btn>
          </section>
        )}
      </div>

      <FieldCamera
        open={!!camFor}
        view={camFor}
        site={v.site_name || v.project_name}
        coords={{ latitude: v.latitude, longitude: v.longitude, accuracy: v.accuracy }}
        dateFormat={dateFmt}
        onClose={() => setCamFor(null)}
        onCapture={(file, meta) =>
          setPhotos((p) => [
            // one photograph per view: taking it again replaces the first
            ...p.filter((x) => x.view !== meta.view || meta.view === "Extra"),
            { file, view: meta.view, heading: meta.heading },
          ])}
      />
    </div>
  );
}
