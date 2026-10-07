import type { HealthReport } from "@/lib/api";

type Row = { label: string; ok: boolean; detail?: string };

export function statusRows(report: HealthReport): Row[] {
  const { worker } = report;
  return [
    { label: "API", ok: true, detail: `v${report.version}` },
    { label: "Database", ok: report.database },
    { label: "Queue (Redis)", ok: report.redis },
    { label: "Storage", ok: report.storage },
    {
      label: "Worker",
      ok: worker.online,
      detail: !worker.online
        ? "offline"
        : worker.state === "loading"
          ? `loading ${worker.engine} model on ${worker.device}`
          : `${worker.engine} engine on ${worker.device} (${worker.capabilities.join(", ")})`,
    },
  ];
}

export function StatusPanel({ report, error }: { report?: HealthReport; error?: Error | null }) {
  if (error) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        {error.message}
      </p>
    );
  }
  if (!report) {
    return <p className="text-zinc-500">Checking services…</p>;
  }
  return (
    <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
      {statusRows(report).map((row) => (
        <li key={row.label} className="flex items-center justify-between gap-4 py-2">
          <span className="flex items-center gap-2">
            <span
              aria-hidden
              className={`inline-block h-2.5 w-2.5 rounded-full ${row.ok ? "bg-emerald-500" : "bg-red-500"}`}
            />
            {row.label}
          </span>
          <span className="text-sm text-zinc-500" data-testid={`status-${row.label}`}>
            {row.detail ?? (row.ok ? "ok" : "down")}
          </span>
        </li>
      ))}
    </ul>
  );
}
