import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeJob } from "@/test/fixtures";

import { JobCard } from "./JobCard";

describe("JobCard", () => {
  it("shows queue position and allows cancelling", () => {
    const onCancel = vi.fn();
    const job = makeJob({ queue_position: 1 });
    render(<JobCard job={job} onCancel={onCancel} />);
    expect(screen.getByTestId("job-stage")).toHaveTextContent("Queued, 1 ahead");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledWith(job);
  });

  it("shows denoising progress while running", () => {
    render(
      <JobCard
        job={makeJob({ status: "running", progress: 0.25, started_at: "2026-10-07T10:00:05Z" })}
      />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByTestId("job-stage")).toHaveTextContent("Denoising step 5 of 20");
  });

  it("plays and offers the video for download when done", () => {
    render(
      <JobCard
        job={makeJob({
          status: "succeeded",
          progress: 1,
          started_at: "2026-10-07T10:00:05Z",
          finished_at: "2026-10-07T10:02:05Z",
          video_url: "/api/jobs/1/video",
          thumbnail_url: "/api/jobs/1/thumbnail",
        })}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Generated video")).toHaveAttribute("src", "/api/jobs/1/video");
    expect(screen.getByRole("link", { name: "Download MP4" })).toHaveAttribute(
      "href",
      "/api/jobs/1/video?download=true",
    );
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.getByText("Generated in 2:00")).toBeInTheDocument();
  });

  it("shows the error when failed", () => {
    render(<JobCard job={makeJob({ status: "failed", error: "Out of GPU memory" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Out of GPU memory");
  });
});
