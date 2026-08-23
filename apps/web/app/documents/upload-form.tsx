"use client";

import { useState } from "react";

async function sha256(file: File) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((b)=>b.toString(16).padStart(2,"0")).join("");
}

export default function UploadForm() {
  const [state,setState]=useState("Select a PDF to upload directly to canonical storage.");
  async function upload(form: FormData) {
    const file=form.get("file") as File; if(!file?.size)return;
    setState("Calculating checksum…");
    const checksum=await sha256(file);
    const auth=await fetch("/api/backend/api/v1/documents/uploads",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({filename:file.name,content_type:file.type||"application/pdf",file_size_bytes:file.size,checksum_sha256:checksum})});
    const payload=await auth.json(); if(!auth.ok){setState(payload.message??"Authorization failed");return}
    setState("Uploading to S3…"); const s3=new FormData(); Object.entries(payload.upload_fields).forEach(([k,v])=>s3.append(k,v as string)); s3.append("file",file);
    const sent=await fetch(payload.upload_url,{method:"POST",body:s3}); if(!sent.ok){setState("S3 upload failed");return}
    await fetch(`/api/backend/api/v1/documents/${payload.document_id}/upload-complete`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({document_version_id:payload.document_version_id})});
    setState(`Queued ingestion job ${payload.ingestion_job_id}`);
  }
  return <form action={upload} className="card"><h2>Upload PDF</h2><p>{state}</p><input name="file" type="file" accept="application/pdf" required/><button style={{marginTop:12}}>Upload securely</button></form>;
}
