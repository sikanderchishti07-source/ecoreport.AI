import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertCircle, ArrowLeft, ArrowRight, BarChart3, CheckCircle2, Clock, Copy,
  Eye, EyeOff, KeyRound, Leaf, Loader2, Lock, Printer, ShieldCheck,
  Smartphone, User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  authLogin, authSetup, authStatus, authVerify, setSession,
} from "@/lib/api";

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

function ErrorPanel({ error }) {
  if (!error) return null;
  return (
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
      <span className="text-[12.5px] leading-relaxed">{error.text}</span>
    </div>
  );
}

export default function LoginPage() {
  const nav = useNavigate();
  const [setupRequired, setSetupRequired] = useState(null); // null = loading
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState({ name: "", username: "", password: "" });
  const [error, setError] = useState(null);

  // "credentials" -> "enroll" -> "codes"   (first time)
  // "credentials" -> "totp"                (every time after)
  const [step, setStep] = useState("credentials");
  const [challenge, setChallenge] = useState(null);
  const [enrol, setEnrol] = useState(null);   // { qr, secret, name }
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState(null);
  const [pending, setPending] = useState(null); // session held until codes saved
  const codeRef = useRef(null);

  useEffect(() => {
    authStatus()
      .then((s) => setSetupRequired(s.setup_required))
      .catch(() => setSetupRequired(false));
  }, []);

  // the code field is the only thing on its screen — put the cursor in it
  useEffect(() => {
    if (step === "totp" || step === "enroll") codeRef.current?.focus();
  }, [step]);

  const set = (k) => (e) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    if (error) setError(null);
  };

  const describe = (err) => {
    const statusCode = err?.response?.status;
    const detail = err?.response?.data?.detail;
    if (statusCode === 429) {
      return { locked: true, text: detail || "Too many failed attempts." };
    }
    if (!statusCode) {
      return {
        locked: false,
        text: "Could not reach the server. Check your connection and try again.",
      };
    }
    return { locked: false, text: detail || "Sign-in failed. Please try again." };
  };

  const startOver = () => {
    setStep("credentials");
    setChallenge(null);
    setEnrol(null);
    setCode("");
    setError(null);
    setForm((f) => ({ ...f, password: "" }));
  };

  const submitCredentials = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = setupRequired ? await authSetup(form) : await authLogin({
        username: form.username,
        password: form.password,
      });
      setChallenge(data.challenge);
      if (data.stage === "enroll") {
        setEnrol({ qr: data.qr, secret: data.secret, name: data.name });
        setStep("enroll");
      } else {
        setStep("totp");
      }
    } catch (err) {
      const described = describe(err);
      setError(described);
      if (!described.locked) setForm((f) => ({ ...f, password: "" }));
    } finally {
      setBusy(false);
    }
  };

  // A six-digit authenticator code, or a recovery code in XXXX-XXXX form.
  // A recovery code always has its hyphen after four characters, so it can
  // never look like six straight digits — the two patterns cannot collide.
  const codeIsComplete = (v) =>
    /^\d{6}$/.test(v) || /^[0-9A-Z]{4}-[0-9A-Z]{4}$/.test(v);

  const submitCode = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = await authVerify({ challenge, code });
      if (data.recovery_codes) {
        // Hold the session back until the codes have been acknowledged. If
        // we signed them in here, the one and only copy of the recovery
        // codes would vanish with the redirect.
        setPending({ token: data.token, user: data.user });
        setRecoveryCodes(data.recovery_codes);
        setStep("codes");
      } else {
        setSession(data.token, data.user);
        toast.success(`Welcome, ${data.user.name}`);
        if (typeof data.recovery_codes_remaining === "number") {
          toast.warning(
            `Recovery code used — ${data.recovery_codes_remaining} left. ` +
            `Ask an admin to reset your authenticator when convenient.`
          );
        }
        nav("/campaigns", { replace: true });
      }
    } catch (err) {
      setError(describe(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  // Submit the moment the code is complete. Nobody types six digits and then
  // wants to reach for a button, and the code expires in thirty seconds.
  // The button stays for anyone who pastes, or uses a keyboard only.
  useEffect(() => {
    if ((step === "totp" || step === "enroll") && !busy
        && codeIsComplete(code)) {
      submitCode();
    }
    // submitCode is redefined every render; the guard above is what makes
    // this safe to run on any change to the code itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, step, busy]);


  const finishEnrolment = () => {
    if (!pending) return;
    setSession(pending.token, pending.user);
    toast.success(`Welcome, ${pending.user.name}`);
    nav("/campaigns", { replace: true });
  };

  const copyCodes = async () => {
    try {
      await navigator.clipboard.writeText((recoveryCodes || []).join("\n"));
      toast.success("Recovery codes copied");
    } catch {
      toast.error("Could not copy — please write them down instead");
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground lg:grid lg:grid-cols-[360px_minmax(0,1fr)] xl:grid-cols-[400px_minmax(0,1fr)]">

      {/* ---------------- brand panel ---------------- */}
      <aside
        className="relative overflow-hidden px-8 py-10 lg:py-12 lg:px-9 lg:rounded-r-3xl"
        style={{ backgroundColor: NAVY }}
      >
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${BG})` }}
          aria-hidden="true"
        />
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

      {/* ---------------- card ---------------- */}
      <main className="relative flex items-center justify-center px-4 py-12 lg:py-16">
        <BackdropPattern />

        <div className="relative w-full max-w-[420px]">
          <div
            className="border border-border rounded-2xl bg-card px-8 py-9"
            style={{ boxShadow: CARD_SHADOW }}
          >
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
            ) : step === "credentials" ? (
              /* ---------------- step 1: password ---------------- */
              <>
                <h1 className="text-[25px] font-semibold tracking-tight">
                  {setupRequired ? "Create the admin account" : "Welcome back"}
                </h1>
                <p className="text-[13.5px] text-muted-foreground mt-2 leading-relaxed">
                  {setupRequired
                    ? "First-time setup — this account manages all other users."
                    : "Sign in to access your dashboard."}
                </p>

                <ErrorPanel error={error} />

                <form onSubmit={submitCredentials} className="mt-8 space-y-[18px]">
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
            ) : step === "enroll" ? (
              /* ---------------- step 2a: first-time enrolment ---------------- */
              <>
                <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
                  <Smartphone className="w-4 h-4" />
                  Two-factor setup
                </div>
                <h1 className="text-[23px] font-semibold tracking-tight mt-2">
                  Set up your authenticator
                </h1>
                <p className="text-[13px] text-muted-foreground mt-2 leading-relaxed">
                  Install Google Authenticator or Microsoft Authenticator on
                  your phone, then scan this code.
                </p>

                <div className="mt-6 flex justify-center">
                  <div className="rounded-xl border border-border bg-white p-3">
                    {enrol?.qr && (
                      <img
                        src={enrol.qr}
                        alt="Scan this code with your authenticator app"
                        width={188}
                        height={188}
                        data-testid="enroll-qr"
                      />
                    )}
                  </div>
                </div>

                {/* a phone camera that will not focus, or a desktop app, needs
                    the secret typed instead */}
                <details className="mt-4 group">
                  <summary className="text-[12px] text-muted-foreground cursor-pointer list-none hover:text-foreground">
                    Can't scan it? Enter this key by hand
                  </summary>
                  <p className="mt-2 font-mono text-[12.5px] tracking-wider break-all rounded-md border border-border bg-secondary/40 px-3 py-2">
                    {enrol?.secret}
                  </p>
                </details>

                <ErrorPanel error={error} />

                <form onSubmit={submitCode} className="mt-6 space-y-3">
                  <Label className="text-[12.5px] text-muted-foreground">
                    Enter the 6-digit code the app shows, or a recovery code
                  </Label>
                  <Input
                    ref={codeRef}
                    value={code}
                    onChange={(e) => {
                      // Two things are typed here: a six-digit code from the
                      // authenticator, and a recovery code like K7QD-2M4X.
                      // Stripping to digits made the second impossible to
                      // enter, which left anyone with a lost phone stuck.
                      setCode(
                        e.target.value
                          .toUpperCase()
                          .replace(/[^0-9A-Z-]/g, "")
                          .slice(0, 9)
                      );
                      if (error) setError(null);
                    }}
                    required
                    inputMode="text"
                    autoComplete="one-time-code"
                    placeholder="000000"
                    className="rounded-[10px] h-12 text-center text-lg tracking-[0.4em] font-mono bg-card"
                    data-testid="totp-code-input"
                  />
                  <Button
                    type="submit"
                    disabled={busy || !codeIsComplete(code)}
                    className="w-full rounded-[10px] h-12 text-[14.5px] text-white hover:opacity-90"
                    style={{ backgroundColor: NAVY, boxShadow: BUTTON_SHADOW }}
                    data-testid="totp-submit-btn"
                  >
                    {busy ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Checking…
                      </>
                    ) : (
                      <>
                        Confirm and continue
                        <ArrowRight className="w-[18px] h-[18px] ml-2" />
                      </>
                    )}
                  </Button>
                  <button
                    type="button"
                    onClick={startOver}
                    className="w-full text-[12px] text-muted-foreground hover:text-foreground inline-flex items-center justify-center gap-1.5 pt-1"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" />
                    Back
                  </button>
                </form>
              </>
            ) : step === "totp" ? (
              /* ---------------- step 2b: routine code ---------------- */
              <>
                <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
                  <ShieldCheck className="w-4 h-4" />
                  Two-factor
                </div>
                <h1 className="text-[25px] font-semibold tracking-tight mt-2">
                  Enter your code
                </h1>
                <p className="text-[13px] text-muted-foreground mt-2 leading-relaxed">
                  Open your authenticator app and type the 6-digit code for
                  EcoReport AI.
                </p>

                <ErrorPanel error={error} />

                <form onSubmit={submitCode} className="mt-7 space-y-3">
                  <Input
                    ref={codeRef}
                    value={code}
                    onChange={(e) => {
                      // recovery codes contain letters and a dash, so only
                      // strip what could never belong to either form
                      setCode(e.target.value.replace(/[^\w-]/g, "").slice(0, 9));
                      if (error) setError(null);
                    }}
                    required
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="000000"
                    className="rounded-[10px] h-12 text-center text-lg tracking-[0.4em] font-mono bg-card uppercase"
                    data-testid="totp-code-input"
                  />
                  <Button
                    type="submit"
                    disabled={busy || code.length < 6}
                    className="w-full rounded-[10px] h-12 text-[14.5px] text-white hover:opacity-90"
                    style={{ backgroundColor: NAVY, boxShadow: BUTTON_SHADOW }}
                    data-testid="totp-submit-btn"
                  >
                    {busy ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Checking…
                      </>
                    ) : (
                      <>
                        Verify
                        <ArrowRight className="w-[18px] h-[18px] ml-2" />
                      </>
                    )}
                  </Button>
                  <p className="text-[11.5px] text-muted-foreground text-center leading-relaxed pt-1">
                    <KeyRound className="w-3.5 h-3.5 inline-block mr-1 -mt-[2px]" />
                    Lost your phone? Type one of your recovery codes instead.
                  </p>
                  <button
                    type="button"
                    onClick={startOver}
                    className="w-full text-[12px] text-muted-foreground hover:text-foreground inline-flex items-center justify-center gap-1.5"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" />
                    Back
                  </button>
                </form>
              </>
            ) : (
              /* ---------------- step 3: recovery codes, shown once ---------------- */
              <>
                <div className="flex items-center gap-2 text-[12px] text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" />
                  Two-factor is on
                </div>
                <h1 className="text-[23px] font-semibold tracking-tight mt-2">
                  Save your recovery codes
                </h1>
                <p className="text-[13px] text-muted-foreground mt-2 leading-relaxed">
                  These are shown once and never again. Print them or write
                  them down and keep them somewhere safe — they are how you get
                  in if you lose your phone. Each one works a single time.
                </p>

                <div
                  className="mt-5 grid grid-cols-2 gap-2 rounded-lg border border-border bg-secondary/40 p-3"
                  data-testid="recovery-codes"
                >
                  {(recoveryCodes || []).map((c) => (
                    <span
                      key={c}
                      className="font-mono text-[13px] tracking-wider text-center py-1"
                    >
                      {c}
                    </span>
                  ))}
                </div>

                <div className="mt-4 flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={copyCodes}
                    className="flex-1 rounded-[10px] h-10 text-[13px]"
                  >
                    <Copy className="w-4 h-4 mr-1.5" />
                    Copy
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => window.print()}
                    className="flex-1 rounded-[10px] h-10 text-[13px]"
                  >
                    <Printer className="w-4 h-4 mr-1.5" />
                    Print
                  </Button>
                </div>

                <Button
                  type="button"
                  onClick={finishEnrolment}
                  className="w-full rounded-[10px] h-12 text-[14.5px] text-white hover:opacity-90 mt-4"
                  style={{ backgroundColor: NAVY, boxShadow: BUTTON_SHADOW }}
                  data-testid="recovery-done-btn"
                >
                  I have saved them — continue
                  <ArrowRight className="w-[18px] h-[18px] ml-2" />
                </Button>
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
