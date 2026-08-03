import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight, BarChart3, Eye, EyeOff, Leaf, Loader2, Lock, ShieldCheck, User,
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
      <g fill="none" stroke="#2F9E63" strokeOpacity="0.16" strokeWidth="1.1">
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

  useEffect(() => {
    authStatus()
      .then((s) => setSetupRequired(s.setup_required))
      .catch(() => setSetupRequired(false));
  }, []);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = setupRequired
        ? await authSetup(form)
        : await authLogin({ username: form.username, password: form.password });
      setSession(data.token, data.user);
      toast.success(`Welcome, ${data.user.name}`);
      nav("/campaigns", { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Sign-in failed");
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
      <main className="relative flex items-center justify-center px-4 py-10 lg:py-14">
        <BackdropPattern />

        <div className="relative w-full max-w-[380px]">
          <div className="border border-border rounded-xl bg-card px-7 py-8">

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
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-8">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Loading…
              </div>
            ) : (
              <>
                <h1 className="text-[22px] font-semibold tracking-tight">
                  {setupRequired ? "Create the admin account" : "Welcome back"}
                </h1>
                <p className="text-[13px] text-muted-foreground mt-1.5 leading-relaxed">
                  {setupRequired
                    ? "First-time setup — this account manages all other users."
                    : "Sign in to access your dashboard."}
                </p>

                <form onSubmit={submit} className="mt-7 space-y-4">
                  {setupRequired && (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">
                        Full name
                      </Label>
                      <Input
                        value={form.name}
                        onChange={set("name")}
                        required
                        placeholder="Eng. Aida Galal"
                        className="rounded-md h-10"
                        data-testid="setup-name-input"
                      />
                    </div>
                  )}

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">
                      Username
                    </Label>
                    <div className="relative">
                      <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                      <Input
                        value={form.username}
                        onChange={set("username")}
                        required
                        autoComplete="username"
                        className="rounded-md h-10 pl-9"
                        data-testid="login-username-input"
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">
                      Password{" "}
                      {setupRequired && (
                        <span className="text-muted-foreground">
                          (min. 8 characters)
                        </span>
                      )}
                    </Label>
                    <div className="relative">
                      <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                      <Input
                        type={showPassword ? "text" : "password"}
                        value={form.password}
                        onChange={set("password")}
                        required
                        minLength={setupRequired ? 8 : undefined}
                        autoComplete={
                          setupRequired ? "new-password" : "current-password"
                        }
                        className="rounded-md h-10 pl-9 pr-10"
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
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        data-testid="login-password-toggle"
                      >
                        {showPassword ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={busy}
                    className="w-full rounded-md h-11 text-[13.5px] text-white hover:opacity-90"
                    style={{ backgroundColor: NAVY }}
                    data-testid="login-submit-btn"
                  >
                    {busy ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Please wait…
                      </>
                    ) : setupRequired ? (
                      <>
                        <ShieldCheck className="w-4 h-4 mr-2" />
                        Create admin account
                      </>
                    ) : (
                      <>
                        Sign in
                        <ArrowRight className="w-4 h-4 ml-2" />
                      </>
                    )}
                  </Button>
                </form>
              </>
            )}
          </div>

          <p className="text-[11px] text-muted-foreground text-center mt-4 leading-relaxed">
            Bander Said Allehiany for Environmental Consultancy
            <br />
            <span className="opacity-75">KSA NCEC 2020 · v0.1.0</span>
          </p>
        </div>
      </main>
    </div>
  );
}
