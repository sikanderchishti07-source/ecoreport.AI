import { useState } from "react";
import { NavLink, Outlet, Link } from "react-router-dom";
import { Activity, Gauge, Ruler, UserRound } from "lucide-react";
import { NAV } from "@/constants/testIds";
import { Toaster } from "sonner";
import { getOperator, setOperator } from "@/lib/api";

const linkBase =
  "px-3 py-2 text-sm rounded-sm border border-transparent hover:bg-zinc-900 hover:border-border transition-colors";
const linkActive = "bg-zinc-900 border-border text-foreground";
const linkIdle = "text-muted-foreground";

export default function AppShell() {
  const [operator, setOperatorState] = useState(getOperator());
  const onOperatorChange = (e) => {
    setOperatorState(e.target.value);
    setOperator(e.target.value);
  };
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto max-w-[1400px] px-4 md:px-6 h-14 flex items-center justify-between">
          <Link
            to="/"
            data-testid={NAV.brand}
            className="flex items-center gap-2 text-sm font-semibold tracking-tight"
          >
            <span className="inline-flex items-center justify-center w-6 h-6 border border-border rounded-sm bg-zinc-900">
              <Activity className="w-3.5 h-3.5 text-primary" />
            </span>
            <span>EcoReport AI</span>
            <span className="ml-2 text-[10px] uppercase tracking-[0.15em] text-muted-foreground border border-border rounded-sm px-1.5 py-0.5">
              Phase 1
            </span>
          </Link>
          <nav className="flex items-center gap-1">
            <div
              className="hidden sm:flex items-center gap-1.5 mr-2 border border-border rounded-sm px-2 h-9 bg-zinc-900/40"
              title="Your name — recorded in the audit trail on every action"
            >
              <UserRound className="w-3.5 h-3.5 text-muted-foreground" />
              <input
                value={operator}
                onChange={onOperatorChange}
                placeholder="Your name"
                className="bg-transparent outline-none text-xs w-28 placeholder:text-muted-foreground"
                data-testid="operator-name-input"
              />
            </div>
            <NavLink
              to="/campaigns"
              data-testid={NAV.campaigns}
              className={({ isActive }) =>
                `${linkBase} ${isActive ? linkActive : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Gauge className="w-3.5 h-3.5" /> Campaigns
            </NavLink>
            <NavLink
              to="/limits"
              data-testid={NAV.limits}
              className={({ isActive }) =>
                `${linkBase} ${isActive ? linkActive : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Ruler className="w-3.5 h-3.5" /> NCEC Limits
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1400px] px-4 md:px-6 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-[1400px] px-4 md:px-6 py-3 text-[11px] text-muted-foreground flex items-center justify-between">
          <span>EcoReport AI — Ambient Air Quality Monitoring</span>
          <span className="font-mono">v0.1.0 · KSA NCEC 2020</span>
        </div>
      </footer>

      <Toaster theme="dark" position="bottom-right" richColors closeButton />
    </div>
  );
}
