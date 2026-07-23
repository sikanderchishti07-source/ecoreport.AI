import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Activity, Loader2, LogIn, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin, authSetup, authStatus, setSession } from "@/lib/api";

export default function LoginPage() {
  const nav = useNavigate();
  const [setupRequired, setSetupRequired] = useState(null); // null = loading
  const [busy, setBusy] = useState(false);
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
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4">
      <div className="w-full max-w-sm border border-border rounded-sm p-6 bg-card">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center justify-center w-7 h-7 border border-border rounded-sm bg-secondary">
            <Activity className="w-4 h-4 text-primary" />
          </span>
          <span className="text-sm font-semibold tracking-tight">EcoReport AI</span>
        </div>

        {setupRequired === null ? (
          <p className="text-xs text-muted-foreground mt-4">Loading…</p>
        ) : (
          <>
            <h1 className="text-lg font-semibold mt-3">
              {setupRequired ? "Create the admin account" : "Sign in"}
            </h1>
            <p className="text-xs text-muted-foreground mt-1">
              {setupRequired
                ? "First-time setup — this account manages all other users."
                : "Enter your credentials to access the report system."}
            </p>

            <form onSubmit={submit} className="mt-5 space-y-3">
              {setupRequired && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Full name</Label>
                  <Input
                    value={form.name}
                    onChange={set("name")}
                    required
                    placeholder="e.g. Eng. Aida Galal"
                    className="rounded-sm h-9"
                    data-testid="setup-name-input"
                  />
                </div>
              )}
              <div className="space-y-1.5">
                <Label className="text-xs">Username</Label>
                <Input
                  value={form.username}
                  onChange={set("username")}
                  required
                  autoComplete="username"
                  className="rounded-sm h-9"
                  data-testid="login-username-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">
                  Password {setupRequired && (
                    <span className="text-muted-foreground">(min. 8 characters)</span>
                  )}
                </Label>
                <Input
                  type="password"
                  value={form.password}
                  onChange={set("password")}
                  required
                  minLength={setupRequired ? 8 : undefined}
                  autoComplete={setupRequired ? "new-password" : "current-password"}
                  className="rounded-sm h-9"
                  data-testid="login-password-input"
                />
              </div>
              <Button
                type="submit"
                disabled={busy}
                className="w-full rounded-sm h-9"
                data-testid="login-submit-btn"
              >
                {busy ? (
                  <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> Please wait…</>
                ) : setupRequired ? (
                  <><ShieldCheck className="w-4 h-4 mr-1.5" /> Create admin account</>
                ) : (
                  <><LogIn className="w-4 h-4 mr-1.5" /> Sign in</>
                )}
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
