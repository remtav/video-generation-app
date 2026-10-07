import { describe, expect, it } from "vitest";

import { workerLabel } from "./WorkerBadge";

const base = { capabilities: ["t2v"], last_seen: 1 };

describe("workerLabel", () => {
  it("covers each worker state", () => {
    expect(workerLabel(undefined)).toBe("Checking worker…");
    expect(workerLabel({ ...base, online: false, state: null, engine: null, device: null })).toBe(
      "Worker offline",
    );
    expect(
      workerLabel({ ...base, online: true, state: "loading", engine: "wan", device: "RTX 3090" }),
    ).toBe("Loading wan model…");
    expect(
      workerLabel({ ...base, online: true, state: "ready", engine: "wan", device: "RTX 3090" }),
    ).toBe("wan on RTX 3090");
  });
});
