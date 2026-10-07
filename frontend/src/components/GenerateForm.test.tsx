import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { presets } from "@/test/fixtures";

import { buildJobRequest, GenerateForm, INITIAL_FORM } from "./GenerateForm";

describe("buildJobRequest", () => {
  it("omits blank optional fields so the server applies defaults", () => {
    expect(buildJobRequest({ ...INITIAL_FORM, prompt: "  a cat  " })).toEqual({
      prompt: "a cat",
      preset: "draft",
      aspect_ratio: "16:9",
    });
  });

  it("includes advanced fields when set", () => {
    expect(
      buildJobRequest({
        ...INITIAL_FORM,
        prompt: "a cat",
        preset: "standard",
        aspectRatio: "9:16",
        seed: "7",
        steps: "25",
        guidanceScale: "4.5",
        negativePrompt: "blurry",
      }),
    ).toEqual({
      prompt: "a cat",
      preset: "standard",
      aspect_ratio: "9:16",
      seed: 7,
      steps: 25,
      guidance_scale: 4.5,
      negative_prompt: "blurry",
    });
  });
});

describe("GenerateForm", () => {
  it("submits the chosen preset and aspect ratio", () => {
    const onSubmit = vi.fn();
    render(<GenerateForm presets={presets} onSubmit={onSubmit} submitting={false} error={null} />);

    const button = screen.getByRole("button", { name: "Generate" });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "a red fox" } });
    fireEvent.click(screen.getByLabelText(/Standard/));
    fireEvent.click(screen.getByLabelText("Portrait 9:16"));
    fireEvent.click(button);

    expect(onSubmit).toHaveBeenCalledWith({
      prompt: "a red fox",
      preset: "standard",
      aspect_ratio: "9:16",
    });
  });

  it("shows preset time estimates and errors", () => {
    render(
      <GenerateForm presets={presets} onSubmit={vi.fn()} submitting={false} error="queue down" />,
    );
    expect(screen.getByText("≈ 3 min")).toBeInTheDocument();
    expect(screen.getByText("≈ 14 min")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("queue down");
  });
});
