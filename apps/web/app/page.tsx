import { api } from "@/lib/api";

type Summary = { total_documents:number; indexed_documents:number; failed_documents:number; recent_queries:number; recent_uploads:number; drive_sync_status:string; system_status:string };

export default async function Dashboard() {
  let data: Summary = { total_documents:0,indexed_documents:0,failed_documents:0,recent_queries:0,recent_uploads:0,drive_sync_status:"NOT_CONFIGURED",system_status:"UNKNOWN" };
  try { data = await api<Summary>("/api/v1/admin/dashboard"); } catch { /* role or API unavailable */ }
  return <>
    <header className="header"><div><div className="eyebrow">Workspace overview</div><h1>Good morning</h1><p>Your governed knowledge base at a glance.</p></div><a className="button" href="/documents">Upload document</a></header>
    <section className="grid stats">
      <div className="card stat"><span className="muted">Total documents</span><strong>{data.total_documents}</strong></div>
      <div className="card stat"><span className="muted">Indexed</span><strong>{data.indexed_documents}</strong></div>
      <div className="card stat"><span className="muted">Failed</span><strong>{data.failed_documents}</strong></div>
      <div className="card stat"><span className="muted">Queries · 7 days</span><strong>{data.recent_queries}</strong></div>
    </section>
    <section className="grid two" style={{marginTop:18}}><div className="card"><h2>Recent activity</h2><p>{data.recent_uploads} uploads in the last seven days.</p><div className="empty">Activity appears as documents and conversations are created.</div></div><div className="card"><h2>System status</h2><p><span className="badge">{data.system_status}</span></p><table><tbody><tr><td>Drive sync</td><td>{data.drive_sync_status}</td></tr><tr><td>API</td><td>Connected</td></tr></tbody></table></div></section>
  </>;
}
