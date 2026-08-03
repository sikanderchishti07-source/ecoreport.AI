import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertCircle, ArrowRight, BarChart3, Clock, Eye, EyeOff, Leaf, Loader2,
  Lock, ShieldCheck, User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, authSetup, authStatus, setSession } from "@/lib/api";

// Brand navy, stated inline rather than through the theme config so the panel
// renders identically whichever mode the app is in.
const NAVY = "#0F3D6E";

// The photograph sits in frontend/public, so it is served from the site root
// and needs no bundler import.
const BG = "/login-bg.jpg";

// Three stacked shadows rather than one. A single blurred shadow reads as a
// sticker; a contact shadow at the edge, a mid shadow and a wide soft one is
// how an object actually sits on a surface. All tinted navy rather than black,
// so the card lifts within the page's own colour instead of dirtying it.
const CARD_SHADOW =
  "0 1px 2px rgba(15,61,110,0.05), 0 8px 20px rgba(15,61,110,0.09), 0 24px 48px rgba(15,61,110,0.10)";
const BUTTON_SHADOW = "0 4px 12px rgba(15,61,110,0.28)";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Secure & Reliable",
    body: "Enterprise-grade security for your data",
  },
  {
    icon: BarChart3,
    title: "Smart Analytics",
    body: "AI-driven insights and automated reporting",
  },
  {
    icon: Leaf,
    title: "Environmental Focus",
    body: "Built for environmental consultancy and compliance",
  },
];

/**
 * The faint pattern behind the sign-in card.
 *
 * Drawn as SVG rather than shipped as an image: it is a handful of paths, it
 * scales to any window without a second asset to load, and its colours come
 * from the brand rather than from a texture file. Two layers, both nearly
 * invisible on purpose — a fine dot grid over the whole area, and contour
 * curves sweeping in from the right edge. Enough that the white half is not a
 * blank page, quiet enough that it never competes with the form.
 */
function BackdropPattern() {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      preserveAspectRatio="none"
      viewBox="0 0 900 700"
      aria-hidden="true"
    >
      <defs>
        <pattern
          id="ecoreport-login-dots"
          width="26"
          height="26"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1.6" cy="1.6" r="1.2" fill={NAVY} opacity="0.07" />
        </pattern>
      </defs>
      <rect width="900" height="700" fill="url(#ecoreport-login-dots)" />
      <g fill="none" stroke="#2F9E63" strokeOpacity="0.15" strokeWidth="1.1">
        <path d="M900 60 C 790 130, 770 220, 850 300 C 925 375, 875 490, 735 595" />
        <path d="M900 118 C 808 182, 790 252, 866 322 C 936 388, 898 498, 782 600" />
        <path d="M900 176 C 828 234, 812 288, 882 344 C 944 396, 922 508, 830 610" />
      </g>
      <g fill="none" stroke="#1F6FB2" strokeOpacity="0.10" strokeWidth="1.1">
        <path d="M120 700 C 178 610, 164 534, 96 488" />
        <path d="M174 700 C 230 616, 218 546, 152 498" />
      </g>
    </svg>
  );
}

export default function LoginPage() {
  const nav = useNavigate();
  const [setupRequired, setSetupRequired] = useState(null); // null = loading
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState({ name: "", username: "", password: "" });
  // { text, locked } — locked distinguishes a throttled name from a bad
  // password, because the two need different wording and a different tone.
  const [error, setError] = useState(null);

  useEffect(() => {
    authStatus()
      .then((s) => setSetupRequired(s.setup_required))
      .catch(() => setSetupRequired(false));
  }, []);

  const set = (k) => (e) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    // clear the message as soon as they start correcting it, so a stale
    // failure is never sitting above a fresh attempt
    if (error) setError(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = setupRequired
        ? await authSetup(form)
        : await authLogin({ username: form.username, password: form.password });
      setSession(data.token, data.user);
      toast.success(`Welcome, ${data.user.name}`);
      nav("/campaigns", { replace: true });
    } catch (err) {
      const statusCode = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (statusCode === 429) {
        setError({
          locked: true,
          text: detail || "Too many failed sign-in attempts. Try again later.",
        });
      } else if (!statusCode) {
        setError({
          locked: false,
          text: "Could not reach the server. Check your connection and try again.",
        });
      } else {
        setError({
          locked: false,
          text: detail || "Sign-in failed. Please try again.",
        });
        setForm((f) => ({ ...f, password: "" }));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    // The panel is a fixed width rather than a fraction of the page: as a
    // proportion it stretched to half a wide monitor, which is what made the
    // photograph dominate.
    <div className="min-h-screen bg-background text-foreground lg:grid lg:grid-cols-[360px_minmax(0,1fr)] xl:grid-cols-[400px_minmax(0,1fr)]">

      {/* ---------------- brand panel ---------------- */}
      {/* On a phone this collapses to a short band above the card rather than
          a half-screen photograph, so the fields stay above the fold. */}
      <aside
        className="relative overflow-hidden px-8 py-10 lg:py-12 lg:px-9 lg:rounded-r-3xl"
        style={{ backgroundColor: NAVY }}
      >
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${BG})` }}
          aria-hidden="true"
        />
        {/* darkest at the top-left where the wording sits, clearing toward the
            bottom-right so the photograph still reads as a photograph */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(155deg, rgba(12,44,83,0.95) 0%, rgba(15,61,110,0.88) 45%, rgba(15,61,110,0.58) 100%)",
          }}
          aria-hidden="true"
        />

        <div className="relative flex h-full flex-col justify-between gap-12">
          <div>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-white/10 border border-white/15">
                <Leaf className="w-5 h-5" style={{ color: "#9FE1CB" }} />
              </span>
              <span className="text-lg font-semibold tracking-tight text-white">
                EcoReport AI
              </span>
            </div>

            <h2 className="mt-9 text-xl font-semibold leading-snug text-white max-w-[15rem]">
              Intelligent Environmental Reporting System
            </h2>
            <div
              className="mt-4 h-[2px] w-8"
              style={{ backgroundColor: "#5DCAA5" }}
            />
            <p
              className="mt-3.5 text-[12.5px] leading-relaxed max-w-[16rem]"
              style={{ color: "#B5D4F4" }}
            >
              AI-powered insights for a sustainable future. Monitor, analyze and
              report with confidence.
            </p>
          </div>

          <ul className="space-y-5">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center min-w-[32px] h-8 rounded-full bg-white/10 border border-white/15">
                  <Icon className="w-4 h-4" style={{ color: "#9FE1CB" }} />
                </span>
                <span>
                  <span className="block text-[12.5px] font-semibold text-white">
                    {title}
                  </span>
                  <span
                    className="block text-[11.5px] leading-relaxed mt-0.5 max-w-[14rem]"
                    style={{ color: "#8FB6DC" }}
                  >
                    {body}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* ---------------- sign-in card ---------------- */}
      <main className="relative flex items-center justify-center px-4 py-12 lg:py-16">
        <BackdropPattern />

        <div className="relative w-full max-w-[420px]">
          <div
            className="border border-border rounded-2xl bg-card px-8 py-9"
            style={{ boxShadow: CARD_SHADOW }}
          >

            {/* the panel above already carries the mark on a wide screen */}
            <div className="flex items-center gap-2.5 lg:hidden mb-7">
              <span
                className="inline-flex items-center justify-center w-8 h-8 rounded-md"
                style={{ backgroundColor: NAVY }}
              >
                <Leaf className="w-4 h-4" style={{ color: "#9FE1CB" }} />
              </span>
              <span className="text-sm font-semibold tracking-tight">
                EcoReport AI
              </span>
            </div>

            {setupRequired === null ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-10">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Loading…
              </div>
            ) : (
              <>
                <h1 className="text-[25px] font-semibold tracking-tight">
                  {setupRequired ? "Create the admin account" : "Welcome back"}
                </h1>
                <p className="text-[13.5px] text-muted-foreground mt-2 leading-relaxed">
                  {setupRequired
                    ? "First-time setup — this account manages all other users."
                    : "Sign in to access your dashboard."}
                </p>

                {/* A failure belongs inside the card, next to the fields that
                    caused it — a toast in the corner is missed, especially on
                    a phone. */}
                {error && (
                  <div
                    role="alert"
                    data-testid="login-error"
                    className={`mt-6 flex items-start gap-2.5 rounded-lg border px-3.5 py-3 ${
                      error.locked
                        ? "border-amber-500/40 bg-amber-500/10"
                        : "border-destructive/40 bg-destructive/10"
                    }`}
                  >
                    {error.locked ? (
                      <Clock className="w-4 h-4 mt-[1px] shrink-0 text-amber-500" />
                    ) : (
                      <AlertCircle className="w-4 h-4 mt-[1px] shrink-0 text-destructive" />
                    )}
                    <span className="text-[12.5px] leading-relaxed">
                      {error.text}
                    </span>
                  </div>
                )}

                <form onSubmit={submit} className="mt-8 space-y-[18px]">
                  {setupRequired && (
                    <div className="space-y-2">
                      <Label className="text-[12.5px] text-muted-foreground">
                        Full name
                      </Label>
                      <Input
                        value={form.name}
                        onChange={set("name")}
                        required
                        placeholder="Eng. Aida Galal"
                        className="rounded-[10px] h-11 text-sm bg-card"
                        data-testid="setup-name-input"
                      />
                    </div>
                  )}

                  <div className="space-y-2">
                    <Label className="text-[12.5px] text-muted-foreground">
                      Username
                    </Label>
                    <div className="relative">
                      <User className="w-[17px] h-[17px] absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                      <Input
                        value={form.username}
                        onChange={set("username")}
                        required
                        autoComplete="username"
                        className="rounded-[10px] h-11 pl-11 text-sm bg-card"
                        data-testid="login-username-input"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-[12.5px] text-muted-foreground">
                      Password{" "}
                      {setupRequired && (
                        <span className="text-muted-foreground">
                          (min. 8 characters)
                        </span>
                      )}
                    </Label>
                    <div className="relative">
                      <Lock className="w-[17px] h-[17px] absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                      <Input
                        type={showPassword ? "text" : "password"}
                        value={form.password}
                        onChange={set("password")}
                        required
                        minLength={setupRequired ? 8 : undefined}
                        autoComplete={
                          setupRequired ? "new-password" : "current-password"
                        }
                        className="rounded-[10px] h-11 pl-11 pr-11 text-sm bg-card"
                        data-testid="login-password-input"
                      />
                      {/* a typo in a masked field is the commonest reason a
                          sign-in fails twice over */}
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label={
                          showPassword ? "Hide password" : "Show password"
                        }
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        data-testid="login-password-toggle"
                      >
                        {showPassword ? (
                          <EyeOff className="w-[17px] h-[17px]" />
                        ) : (
                          <Eye className="w-[17px] h-[17px]" />
                        )}
                      </button>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={busy}
                    className="w-full rounded-[10px] h-12 text-[14.5px] text-white hover:opacity-90 !mt-7"
                    style={{ backgroundColor: NAVY, boxShadow: BUTTON_SHADOW }}
                    data-testid="login-submit-btn"
                  >
                    {busy ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Please wait…
                      </>
                    ) : setupRequired ? (
                      <>
                        <ShieldCheck className="w-[18px] h-[18px] mr-2" />
                        Create admin account
                      </>
                    ) : (
                      <>
                        Sign in
                        <ArrowRight className="w-[18px] h-[18px] ml-2" />
                      </>
                    )}
                  </Button>
                </form>
              </>
            )}
          </div>

          <p className="text-[11px] text-muted-foreground text-center mt-5 leading-relaxed">
            Bander Said Allehiany for Environmental Consultancy
            <br />
            <span className="opacity-75">KSA NCEC 2020 · v0.1.0</span>
          </p>
        </div>
      </main>
    </div>
  );
}
