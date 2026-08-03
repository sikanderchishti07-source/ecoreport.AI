import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Leaf, Loader2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, authSetup, authStatus, setSession } from "@/lib/api";

// The brand navy, stated inline rather than as a Tailwind class so it does not
// depend on the theme config and renders identically in light and dark mode.
const NAVY = "#0F3D6E";

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
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-[380px]">
        <div className="border border-border rounded-md bg-card overflow-hidden">
          {/* one line of brand across the top — ties the app to the report
              cover without taking any vertical space from the form */}
          <div className="h-[3px]" style={{ backgroundColor: NAVY }} />

          <div className="px-7 pt-8 pb-7">
            <div className="flex items-center gap-2.5 mb-8">
              <span
                className="inline-flex items-center justify-center w-7 h-7 rounded-sm"
                style={{ backgroundColor: NAVY }}
              >
                <Leaf className="w-4 h-4" style={{ color: "#9FE1CB" }} />
              </span>
              <span className="text-sm font-semibold tracking-tight">
                EcoReport AI
              </span>
            </div>

            {setupRequired === null ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-6">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Loading…
              </div>
            ) : (
              <>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {setupRequired ? "Create the admin account" : "Sign in"}
                </h1>
                <p className="text-[13px] text-muted-foreground mt-1.5 leading-relaxed">
                  {setupRequired
                    ? "First-time setup — this account manages all other users."
                    : "Enter your credentials to access the report system."}
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
                        className="rounded-sm h-10"
                        data-testid="setup-name-input"
                      />
                    </div>
                  )}

                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">
                      Username
                    </Label>
                    <Input
                      value={form.username}
                      onChange={set("username")}
                      required
                      autoComplete="username"
                      className="rounded-sm h-10"
                      data-testid="login-username-input"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-baseline justify-between">
                      <Label className="text-xs text-muted-foreground">
                        Password{" "}
                        {setupRequired && (
                          <span className="text-muted-foreground">
                            (min. 8 characters)
                          </span>
                        )}
                      </Label>
                      {/* a typo in a masked field is the commonest reason a
                          sign-in fails twice; let the person check it */}
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        className="text-[11px] text-muted-foreground hover:text-foreground"
                        data-testid="login-password-toggle"
                      >
                        {showPassword ? "Hide" : "Show"}
                      </button>
                    </div>
                    <Input
                      type={showPassword ? "text" : "password"}
                      value={form.password}
                      onChange={set("password")}
                      required
                      minLength={setupRequired ? 8 : undefined}
                      autoComplete={
                        setupRequired ? "new-password" : "current-password"
                      }
                      className="rounded-sm h-10"
                      data-testid="login-password-input"
                    />
                  </div>

                  <Button
                    type="submit"
                    disabled={busy}
                    className="w-full rounded-sm h-[42px] text-[13.5px] text-white hover:opacity-90"
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
        </div>

        <p className="text-[11px] text-muted-foreground text-center mt-4 leading-relaxed">
          Bander Said Allehiany for Environmental Consultancy
          <br />
          <span className="opacity-75">KSA NCEC 2020 · v0.1.0</span>
        </p>
      </div>
    </div>
  );
}
