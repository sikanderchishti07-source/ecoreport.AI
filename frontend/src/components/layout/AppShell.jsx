import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, Link, useNavigate } from "react-router-dom";
import {
  Activity, Bell, Gauge, Images, Inbox, LogOut, Ruler, ShieldCheck, Truck,
  UserRound, Users,
} from "lucide-react";
import { NAV } from "@/constants/testIds";
import { Toaster } from "sonner";
import ThemeToggle from "@/components/ThemeToggle";
import {
  clearSession, getUser, listNotifications, markAllNotificationsRead,
  markNotificationRead, reviewQueue,
} from "@/lib/api";

const linkBase =
  "px-3 py-2 text-sm rounded-sm border border-transparent hover:bg-secondary hover:border-border transition-colors";
const linkActive = "bg-secondary border-border text-foreground";
const linkIdle = "text-muted-foreground";

function fmtWhen(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return d.toLocaleDateString();
}

export default function AppShell() {
  const nav = useNavigate();
  const user = getUser();
  const logout = () => {
    clearSession();
    nav("/login", { replace: true });
  };

  // Notification bell. Polled rather than pushed: one small request a minute
  // is far less to go wrong than a websocket, and a review that arrives a
  // minute late costs nothing.
  const [notes, setNotes] = useState([]);
  const [unread, setUnread] = useState(0);
  const [openBell, setOpenBell] = useState(false);
  const bellRef = useRef(null);

  const [waiting, setWaiting] = useState(0);
  const admin = user?.role === "admin";

  const loadNotes = useCallback(async () => {
    try {
      const d = await listNotifications();
      setNotes(d.items || []);
      setUnread(d.unread || 0);
    } catch {
      /* signed out or offline — the bell simply stays quiet */
    }
    if (admin) {
      try {
        const q = await reviewQueue();
        setWaiting(q.length || 0);
      } catch {
        /* the count simply does not show */
      }
    }
  }, [admin]);

  useEffect(() => {
    loadNotes();
    const t = setInterval(loadNotes, 60000);
    return () => clearInterval(t);
  }, [loadNotes]);

  // Click anywhere else closes the panel.
  useEffect(() => {
    const away = (e) => {
      if (bellRef.current && !bellRef.current.contains(e.target)) {
        setOpenBell(false);
      }
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const openNote = async (n) => {
    setOpenBell(false);
    if (!n.read) {
      try {
        const d = await markNotificationRead(n.id);
        setUnread(d.unread ?? 0);
        setNotes((cur) => cur.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      } catch { /* navigating anyway */ }
    }
    if (n.campaign_id) nav(`/campaigns/${n.campaign_id}`);
  };

  const clearAll = async () => {
    try {
      await markAllNotificationsRead();
      setUnread(0);
      setNotes((cur) => cur.map((x) => ({ ...x, read: true })));
    } catch { /* leave the badge as it is */ }
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
            <span className="inline-flex items-center justify-center w-6 h-6 border border-border rounded-sm bg-secondary">
              <Activity className="w-3.5 h-3.5 text-primary" />
            </span>
            <span>EcoReport AI</span>
            <span className="ml-2 text-[10px] uppercase tracking-[0.15em] text-muted-foreground border border-border rounded-sm px-1.5 py-0.5">
              Phase 1
            </span>
          </Link>
          <nav className="flex items-center gap-1">

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
            <NavLink
              to="/labs"
              className={({ isActive }) =>
                `${linkBase} ${isActive ? linkActive : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Truck className="w-3.5 h-3.5" /> Mobile Labs
            </NavLink>
            <NavLink
              to="/cover-photos"
              data-testid="nav-cover-photos"
              className={({ isActive }) =>
                `${linkBase} ${isActive ? linkActive : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Images className="w-3.5 h-3.5" /> Cover Photos
            </NavLink>
            {admin && (
              <NavLink
                to="/review"
                data-testid="nav-review"
                className={({ isActive }) =>
                  `${linkBase} ${isActive ? linkActive : linkIdle} inline-flex items-center gap-1.5`
                }
              >
                <Inbox className="w-3.5 h-3.5" /> Review
                {waiting > 0 && (
                  <span className="ml-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-medium leading-[18px] text-center">
                    {waiting}
                  </span>
                )}
              </NavLink>
            )}
            {admin && (
              <NavLink
                to="/users"
                className={({ isActive }) =>
                  `${linkBase} ${isActive ? linkActive : linkIdle} inline-flex items-center gap-1.5`
                }
              >
                <Users className="w-3.5 h-3.5" /> Users
              </NavLink>
            )}
            <div className="relative" ref={bellRef}>
              <button
                onClick={() => { setOpenBell((v) => !v); if (!openBell) loadNotes(); }}
                title="Notifications"
                data-testid="notifications-btn"
                className={`${linkBase} ${linkIdle} inline-flex items-center gap-1.5 relative`}
              >
                <Bell className="w-3.5 h-3.5" />
                {unread > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-medium leading-4 text-center">
                    {unread > 9 ? "9+" : unread}
                  </span>
                )}
              </button>
              {openBell && (
                <div className="absolute right-0 mt-1 w-[320px] max-h-[380px] overflow-auto border border-border rounded-sm bg-background shadow-lg z-40">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      Notifications
                    </span>
                    {unread > 0 && (
                      <button onClick={clearAll}
                              className="text-[11px] text-primary hover:underline">
                        Mark all read
                      </button>
                    )}
                  </div>
                  {notes.length === 0 ? (
                    <p className="px-3 py-4 text-xs text-muted-foreground">
                      Nothing waiting.
                    </p>
                  ) : (
                    notes.map((n) => (
                      <button
                        key={n.id}
                        onClick={() => openNote(n)}
                        className={`w-full text-left px-3 py-2 border-b border-border last:border-0 hover:bg-secondary transition-colors ${n.read ? "" : "bg-secondary/40"}`}
                      >
                        <div className="text-xs leading-snug">{n.message}</div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          {fmtWhen(n.created_at)}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
            <ThemeToggle />
            <div
              className="hidden sm:flex items-center gap-1.5 ml-2 border border-border rounded-sm px-2.5 h-9 bg-secondary/40 text-xs"
              title={`Signed in as ${user?.name || ""} — all actions are recorded under this name`}
            >
              {admin
                ? <ShieldCheck className="w-3.5 h-3.5 text-primary" />
                : <UserRound className="w-3.5 h-3.5 text-muted-foreground" />}
              <span className="max-w-[140px] truncate">{user?.name || "—"}</span>
            </div>
            <button
              onClick={logout}
              title="Sign out"
              className={`${linkBase} ${linkIdle} inline-flex items-center gap-1.5`}
              data-testid="logout-btn"
            >
              <LogOut className="w-3.5 h-3.5" /> Sign out
            </button>
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
