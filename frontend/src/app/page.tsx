import { SystemStatus } from "./SystemStatus";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-8 px-4 py-12">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">vidgen</h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Self-hosted video generation with Wan 2.2. Generation arrives in Phase 2; this page shows
          the health of the stack.
        </p>
      </header>
      <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-4 text-lg font-medium">System status</h2>
        <SystemStatus />
      </section>
    </main>
  );
}
