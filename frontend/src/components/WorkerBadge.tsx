import type { WorkerStatus } from "@/lib/api";

export function workerLabel(worker: WorkerStatus | undefined): string {
  if (!worker) return "Checking worker…";
  if (!worker.online) return "Worker offline";
  if (worker.state === "loading") return `Loading ${worker.engine} model…`;
  return `${worker.engine} on ${worker.device}`;
}

export function WorkerBadge({ worker }: { worker: WorkerStatus | undefined }) {
  const ready = worker?.online && worker.state !== "loading";
  return (
    <span
      className="flex items-center gap-2 rounded-full border border-zinc-200 px-3 py-1 text-xs dark:border-zinc-800"
      data-testid="worker-badge"
    >
      <span
        aria-hidden
        className={`inline-block h-2 w-2 rounded-full ${
          ready ? "bg-emerald-500" : worker?.online ? "bg-amber-500" : "bg-red-500"
        }`}
      />
      {workerLabel(worker)}
    </span>
  );
}
