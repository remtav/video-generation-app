"use client";

import { useNow } from "@/hooks/useNow";
import { downloadUrl, type Job, type JobStatus, TERMINAL_STATUSES } from "@/lib/api";
import { describeJob, elapsedSeconds, formatClock, formatDuration } from "@/lib/format";

const BADGE: Record<JobStatus, string> = {
  queued: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  running: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  succeeded: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  cancelled: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[status]}`}>
      {status}
    </span>
  );
}

export function JobCard({
  job,
  onCancel,
  cancelling = false,
}: {
  job: Job;
  onCancel?: (job: Job) => void;
  cancelling?: boolean;
}) {
  const active = !TERMINAL_STATUSES.has(job.status);
  const now = useNow(active);
  const { params } = job;
  const percent = Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
  const elapsed =
    job.status === "queued"
      ? elapsedSeconds(job.created_at, null, now)
      : elapsedSeconds(job.started_at, job.finished_at, now);
  const download = downloadUrl(job);

  return (
    <article className="flex flex-col gap-3" aria-label="Current job">
      <div className="flex items-start justify-between gap-3">
        <p className="line-clamp-3 text-sm">{job.prompt}</p>
        <StatusBadge status={job.status} />
      </div>
      <p className="text-xs text-zinc-500">
        {params.preset} · {params.width}×{params.height} · {params.num_frames} frames ·{" "}
        {params.steps} steps · seed {params.seed}
      </p>

      {job.status === "succeeded" && job.video_url ? (
        <video
          key={job.video_url}
          className="w-full rounded-lg bg-black"
          src={job.video_url}
          poster={job.thumbnail_url ?? undefined}
          controls
          loop
          playsInline
          aria-label="Generated video"
        />
      ) : null}

      {active && (
        <div className="flex flex-col gap-2">
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            className="h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
          >
            <div
              className="h-full rounded-full bg-sky-500 transition-[width] duration-500"
              style={{ width: `${job.status === "queued" ? 0 : percent}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-zinc-500">
            <span data-testid="job-stage">{describeJob(job)}</span>
            <span>
              {formatClock(elapsed)}
              {job.est_seconds ? ` / ≈ ${formatDuration(job.est_seconds)}` : ""}
            </span>
          </div>
        </div>
      )}

      {job.status === "failed" && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {job.error ?? "Generation failed"}
        </p>
      )}
      {job.status === "succeeded" && (
        <p className="text-xs text-zinc-500">Generated in {formatClock(elapsed)}</p>
      )}

      <div className="flex gap-2">
        {active && onCancel && (
          <button
            type="button"
            onClick={() => onCancel(job)}
            disabled={cancelling}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-zinc-700"
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        )}
        {download && (
          <a
            href={download}
            download
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            Download MP4
          </a>
        )}
      </div>
    </article>
  );
}
