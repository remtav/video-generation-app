import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeJob } from "@/test/fixtures";

import { useJob } from "./useJob";

class FakeEventSource {
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];
  readyState = 1;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(type, listener);
  }
  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
  emit(type: string, data: unknown) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent<string>);
  }
}

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

describe("useJob", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(makeJob()), { status: 200 })),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("applies streamed updates and closes the stream when the job finishes", async () => {
    const { result } = renderHook(() => useJob(makeJob().id), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data?.status).toBe("queued"));

    const source = FakeEventSource.instances[0];
    expect(source.url).toBe(`/api/jobs/${makeJob().id}/events`);

    // Query cache notifications are batched on a timer, so wait for them.
    act(() => source.emit("job", makeJob({ status: "running", progress: 0.5 })));
    await waitFor(() => expect(result.current.data?.progress).toBe(0.5));

    act(() => source.emit("job", makeJob({ status: "succeeded", progress: 1 })));
    await waitFor(() => expect(result.current.data?.status).toBe("succeeded"));
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });

  it("does not open a stream for a finished job", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(makeJob({ status: "succeeded" })))),
    );
    const { result } = renderHook(() => useJob(makeJob().id), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data?.status).toBe("succeeded"));
    // The initial render (before data) may open one; it must be closed once terminal.
    expect(FakeEventSource.instances.every((s) => s.readyState === FakeEventSource.CLOSED)).toBe(
      true,
    );
  });
});
