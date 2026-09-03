import { api } from "@/lib/api";
import DriveControls, { DriveConnection, QueueHealth } from "./drive-controls";

export default async function Admin() {
  let connections: DriveConnection[] = [];
  let queue: QueueHealth = { enabled: false, dlq_messages: null, alert: false, receipt_counts: {} };
  try {
    [connections, queue] = await Promise.all([
      api<DriveConnection[]>("/api/v1/admin/drive/connections"),
      api<QueueHealth>("/api/v1/admin/ingestion/queue-health"),
    ]);
  } catch {
    // The control surface remains available while the API is disconnected.
  }
  return <>
    <header><div className="eyebrow">Platform control plane</div><h1>Administration</h1><p>Manage durable ingestion and external knowledge sources.</p></header>
    <DriveControls initialConnections={connections} initialQueue={queue} />
  </>;
}
