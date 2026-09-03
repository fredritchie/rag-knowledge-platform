"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = { documentId: string; hasActiveVersion: boolean };

async function errorMessage(response: Response) {
  const payload = await response.json().catch(() => ({}));
  return payload.message ?? payload.code ?? `Request failed (${response.status})`;
}

export default function DocumentActions({ documentId, hasActiveVersion }: Props) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "reindexing" | "deleting">("idle");
  const [message, setMessage] = useState("");

  async function reindex() {
    setState("reindexing");
    setMessage("");
    const response = await fetch(`/api/backend/api/v1/documents/${documentId}/reindex`, {
      method: "POST",
    });
    if (!response.ok) setMessage(await errorMessage(response));
    else {
      const result = await response.json();
      setMessage(`Reindex job ${result.job_id} queued.`);
      router.refresh();
    }
    setState("idle");
  }

  async function remove() {
    if (!window.confirm("Delete this document and its indexed vectors?")) return;
    setState("deleting");
    setMessage("");
    const response = await fetch(`/api/backend/api/v1/documents/${documentId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      setMessage(await errorMessage(response));
      setState("idle");
      return;
    }
    router.push("/documents");
    router.refresh();
  }

  return (
    <div>
      <div className="actions">
        <button
          className="secondary"
          disabled={!hasActiveVersion || state !== "idle"}
          onClick={reindex}
          title={hasActiveVersion ? "Queue this document for reindexing" : "No active version to reindex"}
        >
          {state === "reindexing" ? "Queueing…" : "Reindex"}
        </button>
        <button disabled={state !== "idle"} onClick={remove}>
          {state === "deleting" ? "Deleting…" : "Delete"}
        </button>
      </div>
      {message && <p className="actionMessage" role="status">{message}</p>}
    </div>
  );
}
