"use client";

import { FormEvent, useEffect, useState } from "react";

type Tenant = { id: string; name: string; slug: string };

async function tenants(path = "", method = "GET", body?: unknown) {
  const response = await fetch(`/api/backend/api/v1/tenants${path}`, {
    method, headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.message ?? "Tenant request failed");
  return response.json();
}

export default function TenantControls() {
  const [items, setItems] = useState<Tenant[]>([]);
  const [current, setCurrent] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { void (async () => { try { const [list, active] = await Promise.all([tenants(), tenants("/current")]); setItems(list); setCurrent(active.id); } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to load tenants."); } })(); }, []);
  async function select(tenantId: string) {
    setBusy(true);
    try {
      const response = await fetch("/api/tenant", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ tenant_id: tenantId }) });
      if (!response.ok) throw new Error("Unable to select tenant.");
      window.location.reload();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to select tenant."); setBusy(false); }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); setBusy(true);
    try { const tenant = await tenants("", "POST", { name: data.get("name"), slug: data.get("slug") }); form.reset(); await select(tenant.id); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Unable to create tenant."); setBusy(false); }
  }
  return <section className="card"><h2>Tenant</h2><div className="grid two"><label>Active tenant<select value={current} disabled={busy} onChange={(event) => void select(event.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.slug})</option>)}</select></label><form onSubmit={create}><label>Create tenant<input name="name" placeholder="Tenant name" required /></label><label>Slug<input name="slug" placeholder="acme-engineering" pattern="[a-z0-9]+(-[a-z0-9]+)*" required /></label><button disabled={busy}>Create tenant</button></form></div>{message && <p>{message}</p>}</section>;
}
