"use client";

import type { Job } from "@/lib/api";

import { StatusBadge } from "./JobCard";

export function RecentJobs({
  jobs,
  selectedId,
  onSelect,
}: {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (job: Job) => void;
}) {
  if (jobs.length === 0) {
    return <p className="text-sm text-zinc-500">No videos yet.</p>;
  }
  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {jobs.map((job) => (
        <li key={job.id}>
          <button
            type="button"
            onClick={() => onSelect(job)}
            aria-pressed={job.id === selectedId}
            className={`flex w-full items-center gap-3 rounded-lg border p-2 text-left ${
              job.id === selectedId
                ? "border-zinc-900 dark:border-zinc-100"
                : "border-zinc-200 dark:border-zinc-800"
            }`}
          >
            {job.thumbnail_url ? (
              // Thumbnails are small JPEGs served by the API; no Next image optimisation needed.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={job.thumbnail_url}
                alt=""
                className="h-12 w-20 shrink-0 rounded object-cover"
              />
            ) : (
              <span className="h-12 w-20 shrink-0 rounded bg-zinc-100 dark:bg-zinc-800" />
            )}
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="truncate text-sm">{job.prompt}</span>
              <span className="flex items-center gap-2 text-xs text-zinc-500">
                <StatusBadge status={job.status} />
                {job.params.preset}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
