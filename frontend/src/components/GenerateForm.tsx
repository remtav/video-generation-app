"use client";

import { useState, type FormEvent } from "react";

import type { AspectRatio, JobRequest, Preset, PresetName } from "@/lib/api";
import { formatDuration } from "@/lib/format";

export type FormState = {
  prompt: string;
  preset: PresetName;
  aspectRatio: AspectRatio;
  seed: string;
  negativePrompt: string;
  steps: string;
  guidanceScale: string;
};

export const INITIAL_FORM: FormState = {
  prompt: "",
  preset: "draft",
  aspectRatio: "16:9",
  seed: "",
  negativePrompt: "",
  steps: "",
  guidanceScale: "",
};

/** Turn form fields into an API request; blank optional fields use server defaults. */
export function buildJobRequest(form: FormState): JobRequest {
  const request: JobRequest = {
    prompt: form.prompt.trim(),
    preset: form.preset,
    aspect_ratio: form.aspectRatio,
  };
  if (form.negativePrompt.trim()) request.negative_prompt = form.negativePrompt.trim();
  if (form.seed.trim()) request.seed = Number(form.seed);
  if (form.steps.trim()) request.steps = Number(form.steps);
  if (form.guidanceScale.trim()) request.guidance_scale = Number(form.guidanceScale);
  return request;
}

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900";

export function GenerateForm({
  presets,
  onSubmit,
  submitting,
  error,
}: {
  presets: Preset[];
  onSubmit: (request: JobRequest) => void;
  submitting: boolean;
  error: string | null;
}) {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const selected = presets.find((p) => p.name === form.preset);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.prompt.trim()) return;
    onSubmit(buildJobRequest(form));
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" aria-label="Generate a video">
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Prompt</span>
        <textarea
          className={`${inputClass} min-h-28`}
          value={form.prompt}
          maxLength={2000}
          required
          placeholder="A red fox trotting through fresh snow at sunrise, cinematic, shallow depth of field"
          onChange={(e) => set("prompt", e.target.value)}
        />
      </label>

      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">Preset</legend>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {presets.map((preset) => (
            <label
              key={preset.name}
              className={`cursor-pointer rounded-lg border p-3 text-sm ${
                form.preset === preset.name
                  ? "border-zinc-900 bg-zinc-50 dark:border-zinc-100 dark:bg-zinc-900"
                  : "border-zinc-300 dark:border-zinc-700"
              }`}
            >
              <input
                type="radio"
                name="preset"
                value={preset.name}
                className="sr-only"
                checked={form.preset === preset.name}
                onChange={() => set("preset", preset.name)}
              />
              <span className="font-medium">{preset.label}</span>
              <span className="ml-2 text-zinc-500">≈ {formatDuration(preset.est_seconds)}</span>
              <span className="mt-1 block text-zinc-600 dark:text-zinc-400">
                {preset.description}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Aspect ratio</legend>
        <div className="flex gap-2">
          {(["16:9", "9:16"] as const).map((ratio) => (
            <label
              key={ratio}
              className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${
                form.aspectRatio === ratio
                  ? "border-zinc-900 bg-zinc-50 dark:border-zinc-100 dark:bg-zinc-900"
                  : "border-zinc-300 dark:border-zinc-700"
              }`}
            >
              <input
                type="radio"
                name="aspect"
                value={ratio}
                className="sr-only"
                checked={form.aspectRatio === ratio}
                onChange={() => set("aspectRatio", ratio)}
              />
              {ratio === "16:9" ? "Landscape 16:9" : "Portrait 9:16"}
            </label>
          ))}
        </div>
      </fieldset>

      <details className="rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800">
        <summary className="cursor-pointer font-medium">Advanced</summary>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span>Seed</span>
            <input
              className={inputClass}
              type="number"
              min={0}
              max={4294967295}
              placeholder="random"
              value={form.seed}
              onChange={(e) => set("seed", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>Steps</span>
            <input
              className={inputClass}
              type="number"
              min={1}
              max={60}
              placeholder={selected ? String(selected.steps) : ""}
              value={form.steps}
              onChange={(e) => set("steps", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>Guidance</span>
            <input
              className={inputClass}
              type="number"
              min={1}
              max={10}
              step={0.5}
              placeholder={selected ? String(selected.guidance_scale) : ""}
              value={form.guidanceScale}
              onChange={(e) => set("guidanceScale", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-3">
            <span>Negative prompt</span>
            <textarea
              className={`${inputClass} min-h-16`}
              maxLength={2000}
              placeholder="Wan's recommended negative prompt"
              value={form.negativePrompt}
              onChange={(e) => set("negativePrompt", e.target.value)}
            />
          </label>
        </div>
      </details>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting || !form.prompt.trim()}
        className="rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
      >
        {submitting ? "Submitting…" : "Generate"}
      </button>
    </form>
  );
}
