import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { HealthReport } from "@/lib/api";

import { StatusPanel, statusRows } from "./StatusPanel";

const healthy: HealthReport = {
  status: "ok",
  version: "0.1.0",
  database: true,
  redis: true,
  storage: true,
  worker: {
    online: true,
    engine: "fake",
    capabilities: ["i2v", "t2v"],
    device: "cpu",
    last_seen: 1,
  },
};

describe("statusRows", () => {
  it("describes an online worker", () => {
    const worker = statusRows(healthy).find((r) => r.label === "Worker");
    expect(worker).toEqual({ label: "Worker", ok: true, detail: "fake engine on cpu (i2v, t2v)" });
  });

  it("marks failed services as down", () => {
    const rows = statusRows({ ...healthy, status: "degraded", database: false });
    expect(rows.find((r) => r.label === "Database")?.ok).toBe(false);
  });
});

describe("StatusPanel", () => {
  it("shows a loading state", () => {
    render(<StatusPanel />);
    expect(screen.getByText("Checking services…")).toBeInTheDocument();
  });

  it("shows errors as an alert", () => {
    render(<StatusPanel error={new Error("API unreachable (HTTP 502)")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API unreachable");
  });

  it("renders each service", () => {
    render(
      <StatusPanel
        report={{ ...healthy, redis: false, worker: { ...healthy.worker, online: false } }}
      />,
    );
    expect(screen.getByTestId("status-API")).toHaveTextContent("v0.1.0");
    expect(screen.getByTestId("status-Queue (Redis)")).toHaveTextContent("down");
    expect(screen.getByTestId("status-Worker")).toHaveTextContent("offline");
  });
});
