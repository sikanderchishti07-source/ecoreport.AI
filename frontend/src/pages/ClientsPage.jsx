import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Building2, Link2, Loader2, Pencil, Plus, Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  absorbSpelling, clientCampaigns, createClient, deleteClient, listClients,
  listClientSuggestions, updateClient,
} from "@/lib/api";

const BLANK = {
  legal_name: "", short_name: "", contact_name: "", contact_email: "",
  contact_phone: "", address: "", notes: "",
};

/**
 * The name that prints on a report is the legal name, so it is the field the
 * form leads with. The short name exists only because a column is narrower
 * than a company registration.
 */
function ClientForm({ value, onChange, onSave, onCancel, busy }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="border border-border rounded-sm p-5 space-y-4">
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2">
          <Label className="text-xs">Legal name</Label>
          <Input className="rounded-sm mt-1" value={value.legal_name}
                 placeholder="SAJCO Contracting Co. Ltd."
                 onChange={set("legal_name")} />
          <p className="text-[11px] text-muted-foreground mt-1">
            Printed on every report for this client.
          </p>
        </div>
        <div>
          <Label className="text-xs">Short name</Label>
          <Input className="rounded-sm mt-1" value={value.short_name}
                 placeholder="SAJCO" onChange={set("short_name")} />
        </div>
        <div>
          <Label className="text-xs">Contact name</Label>
          <Input className="rounded-sm mt-1" value={value.contact_name}
                 onChange={set("contact_name")} />
        </div>
        <div>
          <Label className="text-xs">Email</Label>
          <Input className="rounded-sm mt-1" value={value.contact_email}
                 onChange={set("contact_email")} />
        </div>
        <div>
          <Label className="text-xs">Phone</Label>
          <Input className="rounded-sm mt-1" value={value.contact_phone}
                 onChange={set("contact_phone")} />
        </div>
        <div className="sm:col-span-2">
          <Label className="text-xs">Address</Label>
          <Input className="rounded-sm mt-1" value={value.address}
                 onChange={set("address")} />
        </div>
        <div className="sm:col-span-2">
          <Label className="text-xs">Notes</Label>
          <Input className="rounded-sm mt-1" value={value.notes}
                 onChange={set("notes")} />
        </div>
      </div>
      <div className="flex gap-2">
        <Button className="rounded-sm" disabled={busy || !value.legal_name.trim()}
                onClick={onSave}>
          {busy && <Loader2 className="w-4 h-4 mr-2 animate-spin" />} Save
        </Button>
        <Button variant="outline" className="rounded-sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export default function ClientsPage() {
  const [clients, setClients] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [expanded, setExpanded] = useState(null);
  const [campaigns, setCampaigns] = useState([]);

  const load = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([listClients(), listClientSuggestions()]);
      setClients(c);
      setSuggestions(s);
    } catch {
      toast.error("Could not load clients");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      if (editing) {
        await updateClient(editing, form);
        toast.success("Saved");
      } else {
        await createClient(form);
        toast.success("Client created");
      }
      setCreating(false);
      setEditing(null);
      setForm(BLANK);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    try {
      await deleteClient(id);
      toast.success("Client removed");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not remove");
    }
  };

  const absorb = async (clientId, text) => {
    setBusy(true);
    try {
      const r = await absorbSpelling(clientId, text);
      toast.success(`${r.linked} campaign(s) linked`);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not link");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (id) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    try {
      setCampaigns(await clientCampaigns(id));
    } catch {
      setCampaigns([]);
    }
  };

  const startEdit = (c) => {
    setEditing(c.id);
    setCreating(false);
    setForm({
      legal_name: c.legal_name || "", short_name: c.short_name || "",
      contact_name: c.contact_name || "", contact_email: c.contact_email || "",
      contact_phone: c.contact_phone || "", address: c.address || "",
      notes: c.notes || "",
    });
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Building2 className="w-5 h-5 text-primary" /> Clients
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            One record per company. The legal name recorded here is what prints
            on reports for every campaign linked to it.
          </p>
        </div>
        <Button className="rounded-sm"
                onClick={() => { setCreating(true); setEditing(null); setForm(BLANK); }}>
          <Plus className="w-4 h-4 mr-2" /> New client
        </Button>
      </header>

      {(creating || editing) && (
        <ClientForm value={form} onChange={setForm} onSave={save} busy={busy}
                    onCancel={() => { setCreating(false); setEditing(null); }} />
      )}

      {/* The spellings already in the archive, and where they belong.
          Shown above the list because it is the work: a client record with
          no campaigns attached to it has changed nothing. */}
      {suggestions.length > 0 && (
        <section className="border border-border rounded-sm p-5 space-y-3">
          <div>
            <h2 className="text-sm font-semibold">Not yet linked</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Client names typed on campaigns that have no record behind them.
              Linking one spelling links every campaign that uses it, and
              records the spelling so it is recognised next time.
            </p>
          </div>
          {suggestions.map((s) => (
            <div key={s.client_text}
                 className="flex items-center justify-between gap-3 flex-wrap border-t border-border pt-3">
              <div className="min-w-0">
                <span className="text-sm">{s.client_text}</span>
                <span className="text-xs text-muted-foreground ml-2">
                  {s.campaign_count} campaign{s.campaign_count === 1 ? "" : "s"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {s.suggested_client_id ? (
                  <Button size="sm" className="rounded-sm" disabled={busy}
                          onClick={() => absorb(s.suggested_client_id, s.client_text)}>
                    <Link2 className="w-3.5 h-3.5 mr-1.5" />
                    Link to {s.suggested_client_name}
                  </Button>
                ) : (
                  <Select onValueChange={(v) => absorb(v, s.client_text)}>
                    <SelectTrigger className="rounded-sm w-56 h-8 text-xs">
                      <SelectValue placeholder="Link to…" />
                    </SelectTrigger>
                    <SelectContent>
                      {clients.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.short_name || c.legal_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="border border-border rounded-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-secondary/50 text-muted-foreground text-xs">
              <th className="text-left px-4 py-2 font-normal">Client</th>
              <th className="text-left px-4 py-2 font-normal">Contact</th>
              <th className="text-right px-4 py-2 font-normal">Campaigns</th>
              <th className="text-right px-4 py-2 font-normal">Actions</th>
            </tr>
          </thead>
          <tbody>
            {clients.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground text-sm">
                  No clients yet. Create one, then link the spellings above to it.
                </td>
              </tr>
            )}
            {clients.map((c) => (
              <tr key={c.id} className="border-t border-border align-top">
                <td className="px-4 py-3">
                  <button className="text-left" onClick={() => toggle(c.id)}>
                    <span className="font-medium">{c.legal_name}</span>
                    {c.short_name && c.short_name !== c.legal_name && (
                      <span className="text-xs text-muted-foreground ml-2">
                        {c.short_name}
                      </span>
                    )}
                  </button>
                  {c.aliases?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {c.aliases.map((a) => (
                        <Badge key={a} variant="outline"
                               className="rounded-sm text-[10px] font-normal">
                          {a}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {expanded === c.id && (
                    <ul className="mt-2 space-y-0.5">
                      {campaigns.length === 0 && (
                        <li className="text-xs text-muted-foreground">
                          No campaigns linked yet.
                        </li>
                      )}
                      {campaigns.map((cm) => (
                        <li key={cm.id} className="text-xs text-muted-foreground">
                          {cm.project_name}
                          {cm.report_number ? ` · ${cm.report_number}` : ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {c.contact_name || c.contact_email
                    ? (
                      <>
                        {c.contact_name && <div>{c.contact_name}</div>}
                        {c.contact_email && (
                          <div className="text-xs">{c.contact_email}</div>
                        )}
                      </>
                    )
                    : <span className="text-xs">—</span>}
                </td>
                <td className="px-4 py-3 text-right">{c.campaign_count}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" className="rounded-sm"
                            onClick={() => startEdit(c)}>
                      <Pencil className="w-3.5 h-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm"
                            className="rounded-sm text-red-400 hover:text-red-300"
                            onClick={() => remove(c.id)}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <p className="text-xs text-muted-foreground">
        Campaigns without a client record keep the name typed on them and print
        exactly as they always have. Linking is optional.
      </p>
    </div>
  );
}
