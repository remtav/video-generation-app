import type { Job, Preset } from "@/lib/api";

export const presets: Preset[] = [
  {
    name: "draft",
    label: "Draft",
    description: "720p, 2 s preview",
    width: 1280,
    height: 704,
    num_frames: 49,
    fps: 24,
    duration_s: 2.04,
    steps: 20,
    guidance_scale: 5,
    est_seconds: 207,
  },
  {
    name: "standard",
    label: "Standard",
    description: "720p",
    width: 1280,
    height: 704,
    num_frames: 121,
    fps: 24,
    duration_s: 5.04,
    steps: 30,
    guidance_scale: 5,
    est_seconds: 857,
  },
];

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "11111111-2222-3333-4444-555555555555",
    status: "queued",
    mode: "t2v",
    engine: "fake",
    prompt: "a fox in the snow",
    params: {
      preset: "draft",
      aspect_ratio: "16:9",
      width: 1280,
      height: 704,
      num_frames: 49,
      fps: 24,
      steps: 20,
      guidance_scale: 5,
      seed: 42,
      negative_prompt: "",
    },
    progress: 0,
    error: null,
    created_at: "2026-10-07T10:00:00Z",
    started_at: null,
    finished_at: null,
    queue_position: 0,
    est_seconds: 207,
    video_url: null,
    thumbnail_url: null,
    ...overrides,
  };
}
