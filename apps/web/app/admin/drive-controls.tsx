"use client";

import { FormEvent, useState } from "react";

export type DriveConnection = {
  connection_id: string; display_name: string; status: string; sync_status: string;
  last_change_token_present: boolean; last_success_time: string | null; next_sync_at: string | null;
  error_count: number; last_error: string | null;
};
export type QueueHealth = { enabled: boolean; dlq_messages: number | null; alert: boolean; receipt_counts: Record<string,number> };
type DriveError = { id:string; file_id:string; action:string; error:string; created_at:string };
const formatTimestamp = (value:string|null, fallback="—") => value ? new Intl.DateTimeFormat("en-GB",{timeZone:"UTC",dateStyle:"medium",timeStyle:"medium"}).format(new Date(value)) : fallback;

async function call(path:string, method="POST", body?:unknown) {
  const response = await fetch(`/api/backend/api/v1/admin${path}`, {method, headers:{"content-type":"application/json"}, body:body?JSON.stringify(body):undefined});
  if(!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
  return response.json();
}

export default function DriveControls({initialConnections,initialQueue}:{initialConnections:DriveConnection[],initialQueue:QueueHealth}) {
  const [connections,setConnections]=useState(initialConnections); const [queue]=useState(initialQueue);
  const [message,setMessage]=useState(""); const [busy,setBusy]=useState(false); const [errors,setErrors]=useState<DriveError[]>([]);
  async function refresh(){setConnections(await call("/drive/connections","GET"));}
  async function connect(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setMessage("");const form=event.currentTarget;const data=new FormData(form);try{await call("/drive/connections","POST",{display_name:data.get("display_name"),credentials_reference:data.get("credentials_reference")});form.reset();await refresh();setMessage("Drive connected and initial checkpoint queued.");}catch(error){setMessage(String(error));}finally{setBusy(false)}}
  async function action(id:string,name:string,method="POST"){setBusy(true);setMessage("");try{const suffix=name?`/${name}`:"";await call(`/drive/connections/${id}${suffix}`,method);await refresh();setMessage(`Drive ${name||"disconnect"} accepted.`);}catch(error){setMessage(String(error));}finally{setBusy(false)}}
  async function deleteLink(id:string){if(!window.confirm("Delete this Drive link? This stops syncing and removes its checkpoint/history, but does not delete already imported documents or the AWS secret."))return;setBusy(true);setMessage("");try{await call(`/drive/connections/${id}/link`,"DELETE");await refresh();setMessage("Drive link deleted.");}catch(error){setMessage(String(error));}finally{setBusy(false)}}
  async function viewErrors(id:string){setBusy(true);try{setErrors(await call(`/drive/connections/${id}/errors`,"GET"));setMessage("Loaded synchronization errors.");}catch(error){setMessage(String(error));}finally{setBusy(false)}}
  return <div className="grid" style={{marginTop:24}}>
    <section className="grid stats">
      <article className="card stat"><span className="muted">Queue mode</span><strong>{queue.enabled?"Event-driven":"Disabled"}</strong></article>
      <article className="card stat"><span className="muted">DLQ messages</span><strong style={{color:queue.alert?"var(--red)":undefined}}>{queue.dlq_messages ?? "N/A"}</strong></article>
      <article className="card stat"><span className="muted">Processed events</span><strong>{queue.receipt_counts.PROCESSED ?? 0}</strong></article>
      <article className="card stat"><span className="muted">Retrying events</span><strong>{queue.receipt_counts.RETRYING ?? 0}</strong></article>
    </section>
    {queue.alert&&<div className="card" style={{borderColor:"var(--red)"}}><strong>DLQ alert</strong><p>One or more ingestion messages need operator investigation.</p></div>}
    <section className="card"><h2>Connect Google Drive</h2><p>Store OAuth credentials in Secrets Manager and enter only the secret ARN or name.</p><form onSubmit={connect} className="grid two"><label>Display name<input name="display_name" required placeholder="Security standards drive"/></label><label>Credentials reference<input name="credentials_reference" required placeholder="arn:aws:secretsmanager:…"/></label><div><button disabled={busy}>Connect Drive</button></div></form></section>
    <section className="card"><div className="header"><div><h2>Drive connections</h2><p>Schedule, cursor, health, errors, and lifecycle controls.</p></div><button className="secondary" onClick={refresh}>Refresh</button></div>{connections.length===0?<div className="empty">No Drive connection is configured.</div>:<table><thead><tr><th>Connection</th><th>Status</th><th>Last sync</th><th>Errors</th><th>Actions</th></tr></thead><tbody>{connections.map(item=><tr key={item.connection_id}><td><strong>{item.display_name}</strong><div className="muted">Cursor {item.last_change_token_present?"stored":"not initialized"}</div>{item.last_error&&<div style={{color:"var(--red)"}}>{item.last_error}</div>}</td><td><span className={`badge ${item.sync_status==="FAILED"?"failed":""}`}>{item.status} / {item.sync_status}</span></td><td>{formatTimestamp(item.last_success_time,"Never")}<div className="muted">Next: {formatTimestamp(item.next_sync_at)}</div></td><td><button className="secondary" disabled={busy} onClick={()=>viewErrors(item.connection_id)}>View {item.error_count}</button></td><td><div className="actions"><button disabled={busy} onClick={()=>action(item.connection_id,"force-sync")}>Force Sync</button>{item.status==="PAUSED"?<button className="secondary" disabled={busy} onClick={()=>action(item.connection_id,"resume")}>Resume</button>:<button className="secondary" disabled={busy} onClick={()=>action(item.connection_id,"pause")}>Pause</button>}<button className="secondary" disabled={busy} onClick={()=>action(item.connection_id,"","DELETE")}>Disconnect</button><button className="secondary" disabled={busy} onClick={()=>deleteLink(item.connection_id)}>Delete Link</button></div></td></tr>)}</tbody></table>}</section>
    {errors.length>0&&<section className="card"><h2>Synchronization errors</h2><table><thead><tr><th>Time</th><th>File</th><th>Action</th><th>Error</th></tr></thead><tbody>{errors.map(error=><tr key={error.id}><td>{formatTimestamp(error.created_at)}</td><td>{error.file_id}</td><td>{error.action}</td><td>{error.error}</td></tr>)}</tbody></table></section>}
    {message&&<div className="card"><p>{message}</p></div>}
  </div>;
}
