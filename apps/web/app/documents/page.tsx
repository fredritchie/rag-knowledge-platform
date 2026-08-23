import Link from "next/link";
import { api } from "@/lib/api";
import type { Document, Page } from "@/lib/types";
import UploadForm from "./upload-form";

export default async function Documents() {
  let data:Page<Document>={items:[],page:{limit:25,offset:0,total:0}};
  try{data=await api<Page<Document>>("/api/v1/documents?limit=50&sort=updated_at&order=desc")}catch{}
  return <><header className="header"><div><div className="eyebrow">Knowledge inventory</div><h1>Documents</h1><p>{data.page.total} governed documents across connected sources.</p></div></header><div className="grid two"><section className="card"><h2>Document library</h2>{data.items.length?<table><thead><tr><th>Name</th><th>Source</th><th>Status</th><th>Updated</th></tr></thead><tbody>{data.items.map(d=><tr key={d.id}><td><Link href={`/documents/${d.id}`}>{d.filename}</Link></td><td>{d.source}</td><td><span className={`badge ${d.status.includes("FAIL")?"failed":d.status!=="ACTIVE"?"pending":""}`}>{d.status}</span></td><td>{new Date(d.updated_at).toLocaleDateString()}</td></tr>)}</tbody></table>:<div className="empty">No documents yet.</div>}</section><UploadForm/></div></>;
}
