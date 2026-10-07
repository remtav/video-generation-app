export type WorkerStatus = {
  online: boolean;
  state: "loading" | "ready" | null;
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

export type PresetName = "draft" | "standard";
export type AspectRatio = "16:9" | "9:16";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type Preset = {
  name: PresetName;
  label: string;
  description: string;
  width: number;
  height: number;
  num_frames: number;
  fps: number;
  duration_s: number;
  steps: number;
  guidance_scale: number;
  est_seconds: number;
};

export type JobParams = {
  preset: PresetName;
  aspect_ratio: AspectRatio;
  width: number;
  height: number;
  num_frames: number;
  fps: number;
  steps: number;
  guidance_scale: number;
  seed: number;
  negative_prompt: string;
};

export type Job = {
  id: string;
  status: JobStatus;
  mode: "t2v" | "i2v";
  engine: string;
  prompt: string;
  params: JobParams;
  progress: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  queue_position: number | null;
  est_seconds: number | null;
  video_url: string | null;
  thumbnail_url: string | null;
};

export type JobList = { items: Job[]; next_cursor: string | null };

export type JobRequest = {
  prompt: string;
  preset: PresetName;
  aspect_ratio: AspectRatio;
  negative_prompt?: string;
  seed?: number;
  steps?: number;
  guidance_scale?: number;
};

export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    // FastAPI validation errors: [{loc, msg}, ...]
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.slice(1).join(".")}: ${d.msg}`)
        .join("; ");
    }
  } catch {
    // fall through to the status text
  }
  return `HTTP ${res.status} ${res.statusText}`.trim();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export async function fetchHealth(): Promise<HealthReport> {
  const res = await fetch("/api/health", { cache: "no-store" });
  // 503 still carries a full report describing what is down.
  if (!res.ok && res.status !== 503) {
    throw new Error(`API unreachable (HTTP ${res.status})`);
  }
  return (await res.json()) as HealthReport;
}

export const fetchPresets = () => request<Preset[]>("/api/presets");
export const fetchJob = (id: string) => request<Job>(`/api/jobs/${id}`);
export const listJobs = (limit = 12) => request<JobList>(`/api/jobs?limit=${limit}`);
export const cancelJob = (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" });
export const deleteJob = (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" });

export const createJob = (body: JobRequest) =>
  request<Job>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const downloadUrl = (job: Job) => (job.video_url ? `${job.video_url}?download=true` : null);
