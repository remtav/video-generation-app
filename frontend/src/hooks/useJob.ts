"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchJob, type Job, TERMINAL_STATUSES } from "@/lib/api";

/**
 * Follow one job: initial fetch, then live updates over Server-Sent Events.
 * Falls back to polling if the event stream cannot be established.
 */
export function useJob(id: string | null) {
  const queryClient = useQueryClient();
  // Remember which job's stream failed, so switching jobs retries the stream.
  const [failedId, setFailedId] = useState<string | null>(null);
  const streamFailed = id !== null && failedId === id;

  const query = useQuery({
    queryKey: ["job", id],
    queryFn: () => fetchJob(id as string),
    enabled: id !== null,
    refetchInterval: (q) => {
      const job = q.state.data;
      return streamFailed && job && !TERMINAL_STATUSES.has(job.status) ? 3000 : false;
    },
  });

  const terminal = query.data ? TERMINAL_STATUSES.has(query.data.status) : false;

  useEffect(() => {
    if (id === null || terminal || typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/jobs/${id}/events`);
    source.addEventListener("job", (event) => {
      const job = JSON.parse((event as MessageEvent<string>).data) as Job;
      queryClient.setQueryData(["job", id], job);
      if (TERMINAL_STATUSES.has(job.status)) {
        source.close();
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      }
    });
    source.onerror = () => {
      // The browser retries on its own; only give up when it has closed the stream.
      if (source.readyState === EventSource.CLOSED) setFailedId(id);
    };
    return () => source.close();
  }, [id, terminal, queryClient]);

  return query;
}
