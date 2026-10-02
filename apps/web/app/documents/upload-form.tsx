"use client";

import { useState } from "react";
import { uploadDocument } from "../../lib/upload";

export default function UploadForm() {
  const [state,setState]=useState("Select a PDF to upload directly to canonical storage.");
  const [busy, setBusy] = useState(false);
  async function upload(form: FormData) {
    const file=form.get("file") as File; if(!file?.size || busy)return;
    setBusy(true);
    try { await uploadDocument(file, setState); }
    finally { setBusy(false); }
  }
  return <form action={upload} className="card"><h2>Upload PDF</h2><p role="status" aria-live="polite">{state}</p><input name="file" type="file" accept="application/pdf" required disabled={busy}/><button style={{marginTop:12}} disabled={busy}>{busy ? "Uploading…" : "Upload securely"}</button></form>;
}
