import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Loader2, LockOpen, Plus, ShieldCheck, ShieldOff, Smartphone, UserRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  createUser, getUser, listUsers, resetUserTwoFactor, unlockUser, updateUser,
} from "@/lib/api";

export default function UsersPage() {
  const me = getUser();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: "", username: "", password: "", role: "member",
  });

  const load = () =>
    listUsers()
      .then(setUsers)
      .catch(() => toast.error("Failed to load users"))
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const onCreate = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createUser(form);
      toast.success(`User "${form.username}" created`);
      setForm({ name: "", username: "", password: "", role: "member" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const patch = async (id, payload, okMsg) => {
    try {
      await updateUser(id, payload);
      toast.success(okMsg);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Update failed");
    }
  };

  const resetPassword = (u) => {
    const pw = window.prompt(`New password for ${u.username} (min. 8 chars):`);
    if (!pw) return;
    if (pw.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    patch(u.id, { password: pw }, "Password reset");
  };

  // Lost phone. Wipes the authenticator setup and the old recovery codes;
  // their next sign-in shows a fresh QR code.
  const resetTwoFactor = async (u) => {
    try {
      await resetUserTwoFactor(u.id);
      toast.success(
        `Two-factor cleared for ${u.username} — they will set it up again at ` +
        `their next sign-in`
      );
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not reset two-factor");
    }
  };

  // Frees someone shut out by five failed attempts, rather than making them
  // wait out the fifteen minutes with an admin standing next to them.
  const unlock = async (u) => {
    try {
      await unlockUser(u.id);
      toast.success(`${u.username} can sign in again`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not unlock");
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Accounts for the report system. Every action each user takes is
          recorded in the audit trail under their name.
        </p>
      </header>

      {/* Create user */}
      <form
        onSubmit={onCreate}
        className="border border-border rounded-sm p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end"
      >
        <div className="space-y-1.5">
          <Label className="text-xs">Full name</Label>
          <Input value={form.name} onChange={set("name")} required
                 className="rounded-sm h-9" placeholder="Eng. …" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Username</Label>
          <Input value={form.username} onChange={set("username")} required
                 minLength={3} className="rounded-sm h-9" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Password (min. 8)</Label>
          <Input type="password" value={form.password} onChange={set("password")}
                 required minLength={8} className="rounded-sm h-9" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Role</Label>
          <Select value={form.role}
                  onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
            <SelectTrigger className="rounded-sm h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="member">Member</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={busy} className="rounded-sm h-9">
          {busy ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                : <Plus className="w-4 h-4 mr-1.5" />}
          Add user
        </Button>
      </form>

      <p className="text-[11px] text-muted-foreground -mt-3">
        A new account has no authenticator yet. The person sets one up at their
        first sign-in — tell them to install Google Authenticator first, and to
        keep the recovery codes it shows them.
      </p>

      {/* Users table */}
      <div className="border border-border rounded-sm">
        {loading ? (
          <p className="text-sm text-muted-foreground p-4">Loading…</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">User</TableHead>
                <TableHead className="text-xs">Username</TableHead>
                <TableHead className="text-xs">Role</TableHead>
                <TableHead className="text-xs">Two-factor</TableHead>
                <TableHead className="text-xs">Active</TableHead>
                <TableHead className="text-xs text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="text-sm">
                    <span className="inline-flex items-center gap-1.5">
                      {u.role === "admin"
                        ? <ShieldCheck className="w-3.5 h-3.5 text-primary" />
                        : <UserRound className="w-3.5 h-3.5 text-muted-foreground" />}
                      {u.name}
                      {u.id === me?.id && (
                        <Badge variant="outline" className="rounded-sm ml-1">you</Badge>
                      )}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs font-mono">{u.username}</TableCell>
                  <TableCell>
                    <Select
                      value={u.role}
                      onValueChange={(v) =>
                        patch(u.id, { role: v }, `Role changed to ${v}`)}
                      disabled={u.id === me?.id}
                    >
                      <SelectTrigger className="rounded-sm h-8 w-[110px] text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="member">Member</SelectItem>
                        <SelectItem value="admin">Admin</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    {u.totp_enabled ? (
                      <span
                        className="inline-flex items-center gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-400"
                        data-testid={`user-2fa-on-${u.id}`}
                      >
                        <Smartphone className="w-3.5 h-3.5" />
                        Set up
                      </span>
                    ) : (
                      <span
                        className="inline-flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400"
                        data-testid={`user-2fa-off-${u.id}`}
                        title="They will be asked to set it up at their next sign-in"
                      >
                        <ShieldOff className="w-3.5 h-3.5" />
                        Not yet
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={u.active !== false}
                      onCheckedChange={(v) =>
                        patch(u.id, { active: v },
                              v ? "Account activated" : "Account deactivated")}
                      disabled={u.id === me?.id}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="inline-flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-sm h-8 text-xs"
                        onClick={() => unlock(u)}
                        title="Clear a lockout from failed sign-in attempts"
                      >
                        <LockOpen className="w-3.5 h-3.5 mr-1" />
                        Unlock
                      </Button>

                      {u.totp_enabled && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              className="rounded-sm h-8 text-xs"
                              data-testid={`user-reset-2fa-${u.id}`}
                            >
                              Reset 2FA
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent className="rounded-sm">
                            <AlertDialogHeader>
                              <AlertDialogTitle>
                                Reset two-factor for {u.username}?
                              </AlertDialogTitle>
                              <AlertDialogDescription>
                                Their authenticator setup and all their unused
                                recovery codes stop working immediately. At
                                their next sign-in they scan a new code and
                                receive a new set. Do this when someone has
                                lost their phone.
                                {u.id === me?.id && (
                                  <span className="block mt-2 text-amber-500">
                                    This is your own account. Have your phone
                                    with you before you confirm.
                                  </span>
                                )}
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel className="rounded-sm">
                                Cancel
                              </AlertDialogCancel>
                              <AlertDialogAction
                                className="rounded-sm"
                                onClick={() => resetTwoFactor(u)}
                              >
                                Reset two-factor
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}

                      <Button
                        variant="outline"
                        size="sm"
                        className="rounded-sm h-8 text-xs"
                        onClick={() => resetPassword(u)}
                      >
                        Reset password
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
