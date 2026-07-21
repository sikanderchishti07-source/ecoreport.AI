import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Plus, ShieldCheck, UserRound } from "lucide-react";
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
import { createUser, getUser, listUsers, updateUser } from "@/lib/api";

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
                    <Switch
                      checked={u.active !== false}
                      onCheckedChange={(v) =>
                        patch(u.id, { active: v },
                              v ? "Account activated" : "Account deactivated")}
                      disabled={u.id === me?.id}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-sm h-8 text-xs"
                      onClick={() => resetPassword(u)}
                    >
                      Reset password
                    </Button>
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
