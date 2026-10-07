import { describe, expect, it } from "vitest";

import { makeJob } from "@/test/fixtures";

import { describeJob, elapsedSeconds, formatClock, formatDuration } from "./format";

describe("formatDuration", () => {
  it.each([
    [0, "0 s"],
    [45, "45 s"],
    [120, "2 min"],
    [600, "10 min"],
    [3900, "1 h 05 min"],
  ])("%d s -> %s", (input, expected) => {
    expect(formatDuration(input)).toBe(expected);
  });
});

describe("formatClock", () => {
  it.each([
    [5, "0:05"],
    [65, "1:05"],
    [3725, "1:02:05"],
  ])("%d s -> %s", (input, expected) => {
    expect(formatClock(input)).toBe(expected);
  });
});

describe("elapsedSeconds", () => {
  it("measures until now or until the end time", () => {
    const now = Date.parse("2026-10-07T10:01:00Z");
    expect(elapsedSeconds("2026-10-07T10:00:00Z", null, now)).toBe(60);
    expect(elapsedSeconds("2026-10-07T10:00:00Z", "2026-10-07T10:00:30Z", now)).toBe(30);
    expect(elapsedSeconds(null)).toBe(0);
  });
});

describe("describeJob", () => {
  it("describes the queue", () => {
    expect(describeJob(makeJob({ queue_position: 0 }))).toBe("Queued, starting next");
    expect(describeJob(makeJob({ queue_position: 2 }))).toBe("Queued, 2 ahead");
  });

  it("describes denoising progress and the final decode", () => {
    expect(describeJob(makeJob({ status: "running", progress: 0 }))).toBe("Starting…");
    expect(describeJob(makeJob({ status: "running", progress: 0.5 }))).toBe(
      "Denoising step 10 of 20",
    );
    expect(describeJob(makeJob({ status: "running", progress: 1 }))).toBe(
      "Decoding and encoding video…",
    );
  });

  it("shows the failure reason", () => {
    expect(describeJob(makeJob({ status: "failed", error: "Out of GPU memory" }))).toBe(
      "Out of GPU memory",
    );
  });
});
