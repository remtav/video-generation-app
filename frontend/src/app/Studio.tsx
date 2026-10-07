"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { GenerateForm } from "@/components/GenerateForm";
import { JobCard } from "@/components/JobCard";
import { RecentJobs } from "@/components/RecentJobs";
import { StatusPanel } from "@/components/StatusPanel";
import { WorkerBadge } from "@/components/WorkerBadge";
import { useJob } from "@/hooks/useJob";
import {
  cancelJob,
  createJob,
  fetchHealth,
  fetchPresets,
  type Job,
  listJobs,
  TERMINAL_STATUSES,
} from "@/lib/api";

const section = "rounded-xl border border-zinc-200 p-5 dark:border-zinc-800";

export function Studio() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 5000 });
  const presets = useQuery({ queryKey: ["presets"], queryFn: fetchPresets, staleTime: Infinity });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => listJobs(12),
    refetchInterval: (q) =>
      q.state.data?.items.some((j) => !TERMINAL_STATUSES.has(j.status)) ? 5000 : 30000,
  });

  const currentId = selectedId ?? jobs.data?.items[0]?.id ?? null;
  const current = useJob(currentId);

  const create = useMutation({
    mutationFn: createJob,
    onSuccess: (job) => {
      queryClient.setQueryData(["job", job.id], job);
      setSelectedId(job.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const cancel = useMutation({
    mutationFn: (job: Job) => cancelJob(job.id),
    onSuccess: (job) => queryClient.setQueryData(["job", job.id], job),
  });

  // Show the live state of the current job in the list too.
  const recent = (jobs.data?.items ?? []).map((j) =>
    current.data && j.id === current.data.id ? current.data : j,
  );

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">vidgen</h1>
          <p className="text-sm text-zinc-500">Text-to-video with Wan 2.2, on your own GPU.</p>
        </div>
        <WorkerBadge worker={health.data?.worker} />
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className={section}>
          <h2 className="mb-4 text-lg font-medium">Create</h2>
          {presets.data ? (
            <GenerateForm
              presets={presets.data}
              onSubmit={(request) => create.mutate(request)}
              submitting={create.isPending}
              error={create.error?.message ?? null}
            />
          ) : (
            <p className="text-sm text-zinc-500">
              {presets.error ? `Cannot reach the API: ${presets.error.message}` : "Loading…"}
            </p>
          )}
        </section>

        <section className={section}>
          <h2 className="mb-4 text-lg font-medium">Current video</h2>
          {current.data ? (
            <JobCard
              job={current.data}
              onCancel={(job) => cancel.mutate(job)}
              cancelling={cancel.isPending && cancel.variables?.id === current.data.id}
            />
          ) : (
            <p className="text-sm text-zinc-500">
              {current.error ? current.error.message : "Your next video will appear here."}
            </p>
          )}
        </section>
      </div>

      <section className={section}>
        <h2 className="mb-4 text-lg font-medium">Recent</h2>
        <RecentJobs jobs={recent} selectedId={currentId} onSelect={(j) => setSelectedId(j.id)} />
      </section>

      <details className={section}>
        <summary className="cursor-pointer text-lg font-medium">System status</summary>
        <div className="mt-4">
          <StatusPanel report={health.data} error={health.error} />
        </div>
      </details>
    </main>
  );
}
