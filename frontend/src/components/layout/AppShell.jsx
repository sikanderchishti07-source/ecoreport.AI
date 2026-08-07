import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, Link, useNavigate } from "react-router-dom";
import {
  Bell, ChevronDown, FlaskConical, Gauge, Images, Inbox, LogOut, Ruler, Truck,
  Users,
} from "lucide-react";
import { NAV } from "@/constants/testIds";
import { Toaster } from "sonner";
import ThemeToggle from "@/components/ThemeToggle";
import {
  clearSession, getUser, listNotifications, markAllNotificationsRead,
  markNotificationRead, reviewQueue,
} from "@/lib/api";

/** Initials for the avatar: two letters at most, and the first letter of the
 *  name when there is only one word. */
function initials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "—";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : ""))
    .toUpperCase();
}

const linkBase =
  "relative px-3 py-2 text-[13px] rounded-md transition-colors";
// The current page is marked by a rule beneath it, aligned to the header's
// own bottom edge. Quieter than a filled pill, and it stops the navigation
// competing with the controls on the right.
const linkActive = "text-foreground font-semibold";
const linkIdle = "text-muted-foreground hover:text-foreground hover:bg-secondary/60";
const linkRule =
  "after:absolute after:left-3 after:right-3 after:-bottom-[13px] after:h-[2px] "
  + "after:rounded-full after:bg-primary";

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
  const [openAcct, setOpenAcct] = useState(false);
  const acctRef = useRef(null);

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

  // Click anywhere else closes whichever panel is open, and Escape closes
  // both — a menu that can only be dismissed by finding its own button again
  // is the sort of thing people quietly resent.
  useEffect(() => {
    const away = (e) => {
      if (bellRef.current && !bellRef.current.contains(e.target)) {
        setOpenBell(false);
      }
      if (acctRef.current && !acctRef.current.contains(e.target)) {
        setOpenAcct(false);
      }
    };
    const esc = (e) => {
      if (e.key === "Escape") { setOpenBell(false); setOpenAcct(false); }
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
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
          {/* A brand lockup rather than a word among the links: the real mark
              at its own proportions, then a rule before the navigation.
              "Phase 1" is gone — it stopped being true months ago, and a label
              that is no longer true teaches people to ignore labels. This says
              which system you are looking at, which stays useful. */}
          <div className="flex items-center gap-3 pr-4 mr-1 border-r border-border/70">
            <Link to="/" data-testid={NAV.brand} className="flex items-center gap-2.5">
              <img
                src="/logo-mark.png"
                alt="BSA.lab"
                className="h-6 w-auto dark:hidden"
              />
              <img
                src="/logo-mark-light.png"
                alt="BSA.lab"
                className="h-6 w-auto hidden dark:block"
              />
            </Link>
            <span className="hidden md:inline text-[9.5px] font-bold uppercase
                             tracking-[0.12em] text-emerald-700 dark:text-emerald-400
                             bg-emerald-50 dark:bg-emerald-400/10
                             border border-emerald-200 dark:border-emerald-400/25
                             rounded px-1.5 py-[3px]">
              Live
            </span>
          </div>
          <nav className="flex items-center gap-1">

            <NavLink
              to="/campaigns"
              data-testid={NAV.campaigns}
              className={({ isActive }) =>
                `${linkBase} ${isActive ? `${linkActive} ${linkRule}` : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Gauge className="w-3.5 h-3.5" /> Campaigns
            </NavLink>
            <NavLink
              to="/limits"
              data-testid={NAV.limits}
              className={({ isActive }) =>
                `${linkBase} ${isActive ? `${linkActive} ${linkRule}` : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Ruler className="w-3.5 h-3.5" /> Limits
            </NavLink>
            <NavLink
              to="/labs"
              className={({ isActive }) =>
                `${linkBase} ${isActive ? `${linkActive} ${linkRule}` : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Truck className="w-3.5 h-3.5" /> Mobile Labs
            </NavLink>
            <NavLink
              to="/site-samples"
              data-testid="nav-site-samples"
              className={({ isActive }) =>
                `${linkBase} ${isActive ? `${linkActive} ${linkRule}` : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <FlaskConical className="w-3.5 h-3.5" /> Site Samples
            </NavLink>
            <NavLink
              to="/cover-photos"
              data-testid="nav-cover-photos"
              className={({ isActive }) =>
                `${linkBase} ${isActive ? `${linkActive} ${linkRule}` : linkIdle} inline-flex items-center gap-1.5`
              }
            >
              <Images className="w-3.5 h-3.5" /> Cover Photos
            </NavLink>
            {admin && (
              <NavLink
                to="/review"
                data-testid="nav-review"
                className={({ isActive }) =>
                  `${linkBase} ${isActive ? `${linkActive} ${linkRule}` : linkIdle} inline-flex items-center gap-1.5`
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
            {/* Theme, users, audit and sign-out live behind the name: things
                touched once a day, not once a minute. Moving them out is what
                gives the navigation room to sit on one line instead of every
                label wrapping. */}
            <span className="w-px h-5 bg-border/70 mx-1" />
            <div className="relative" ref={acctRef}>
              <button
                onClick={() => setOpenAcct((o) => !o)}
                data-testid="account-btn"
                title={`Signed in as ${user?.name || ""} — every action is recorded under this name`}
                className="flex items-center gap-2 h-8 pl-1 pr-2.5 rounded-full
                           border border-border bg-background hover:bg-secondary/60
                           transition-colors"
              >
                <span className="grid place-items-center w-6 h-6 rounded-full
                                 bg-primary text-primary-foreground text-[10px] font-bold">
                  {initials(user?.name)}
                </span>
                <span className="hidden sm:inline text-[12.5px] max-w-[110px] truncate">
                  {(user?.name || "—").split(" ")[0]}
                </span>
                <ChevronDown className="w-3 h-3 text-muted-foreground" />
              </button>

              {openAcct && (
                <div className="absolute right-0 mt-1.5 w-[236px] rounded-md border
                                border-border bg-background shadow-lg z-40 p-1.5">
                  <div className="px-2 py-1.5">
                    <div className="text-[13px] font-semibold leading-tight">
                      {user?.name || "—"}
                    </div>
                    <div className="text-[11px] text-muted-foreground font-mono">
                      {user?.username}{admin ? " · administrator" : ""}
                    </div>
                  </div>
                  <div className="h-px bg-border my-1.5" />
                  <div className="px-2 pt-1 pb-1.5 text-[9.5px] font-bold uppercase
                                  tracking-[0.12em] text-muted-foreground">
                    Appearance
                  </div>
                  <div className="px-1 pb-1.5"><ThemeToggle /></div>
                  {admin && (
                    <>
                      <div className="h-px bg-border my-1.5" />
                      <button
                        onClick={() => { setOpenAcct(false); nav("/users"); }}
                        className="w-full text-left px-2 py-1.5 rounded text-[12.5px]
                                   hover:bg-secondary inline-flex items-center gap-2"
                      >
                        <Users className="w-3.5 h-3.5 text-muted-foreground" /> Users
                      </button>
                    </>
                  )}
                  <div className="h-px bg-border my-1.5" />
                  <button
                    onClick={logout}
                    data-testid="logout-btn"
                    className="w-full text-left px-2 py-1.5 rounded text-[12.5px]
                               text-destructive hover:bg-destructive/10
                               inline-flex items-center gap-2"
                  >
                    <LogOut className="w-3.5 h-3.5" /> Sign out
                  </button>
                </div>
              )}
            </div>
          </nav>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-[1400px] px-4 md:px-6 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-[1400px] px-4 md:px-6 py-3 text-[11px] text-muted-foreground flex items-center justify-between">
          <span>EcoReport AI — environmental monitoring reports</span>
          <span className="font-mono">v0.1.0 · KSA NCEC 2020</span>
        </div>
      </footer>

      <Toaster theme="dark" position="bottom-right" richColors closeButton />
    </div>
  );
}
