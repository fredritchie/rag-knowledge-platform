export async function uploadDocument(file: File, report: (message: string) => void) {
  try {
    report("Calculating checksum…");
    const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    const checksum = [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, "0")).join("");
    const auth = await fetch("/api/backend/api/v1/documents/uploads", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ filename: file.name, content_type: file.type || "application/pdf",
        file_size_bytes: file.size, checksum_sha256: checksum }),
    });
    const payload = await auth.json();
    if (!auth.ok) throw new Error(payload.message ?? "Upload authorization failed. Please sign in and retry.");
    report("Uploading to S3…");
    const form = new FormData();
    Object.entries(payload.upload_fields).forEach(([key, value]) => form.append(key, value as string));
    form.append("file", file);
    const sent = await fetch(payload.upload_url, { method: "POST", body: form });
    if (!sent.ok) throw new Error(`Storage upload failed (${sent.status}). Please retry after checking storage access.`);
    report("Confirming upload…");
    const complete = await fetch(`/api/backend/api/v1/documents/${payload.document_id}/upload-complete`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ document_version_id: payload.document_version_id }),
    });
    if (!complete.ok) throw new Error(`File sent, but upload confirmation failed (${complete.status}). Check Ingestion before retrying.`);
    report("Upload received. Check Ingestion for processing status.");
  } catch (error) {
    report(error instanceof TypeError
      ? "Upload interrupted by a network or storage CORS error. Please retry after checking connectivity and bucket CORS."
      : error instanceof Error ? error.message : "Upload failed. Please retry.");
  }
}
