import type { Job } from "./api";

/** "45 s", "3 min", "1 h 05 min" */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.round(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  return `${h} h ${String(minutes % 60).padStart(2, "0")} min`;
}

/** "1:05" style clock for elapsed time. */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Seconds between two ISO timestamps (or until now). */
export function elapsedSeconds(fromIso: string | null, toIso?: string | null, now = Date.now()) {
  if (!fromIso) return 0;
  const end = toIso ? Date.parse(toIso) : now;
  return Math.max(0, (end - Date.parse(fromIso)) / 1000);
}

/** One-line human description of where a job is. */
export function describeJob(job: Job): string {
  switch (job.status) {
    case "queued":
      return job.queue_position ? `Queued, ${job.queue_position} ahead` : "Queued, starting next";
    case "running": {
      if (job.progress >= 1) return "Decoding and encoding video…";
      const step = Math.round(job.progress * job.params.steps);
      return step === 0 ? "Starting…" : `Denoising step ${step} of ${job.params.steps}`;
    }
    case "succeeded":
      return "Done";
    case "failed":
      return job.error ?? "Failed";
    case "cancelled":
      return "Cancelled";
  }
}
