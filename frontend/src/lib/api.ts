export type WorkerStatus = {
  online: boolean;
  engine: string | null;
  capabilities: string[];
  device: string | null;
  last_seen: number | null;
};

export type HealthReport = {
  status: "ok" | "degraded";
  version: string;
  database: boolean;
  redis: boolean;
  storage: boolean;
  worker: WorkerStatus;
};

export async function fetchHealth(): Promise<HealthReport> {
  const res = await fetch("/api/health", { cache: "no-store" });
  // 503 still carries a full report describing what is down.
  if (!res.ok && res.status !== 503) {
    throw new Error(`API unreachable (HTTP ${res.status})`);
  }
  return (await res.json()) as HealthReport;
}
