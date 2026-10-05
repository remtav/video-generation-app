"""Encode engine output to browser-friendly H.264 MP4 and extract a thumbnail."""

from pathlib import Path

import imageio.v2 as imageio
from PIL import Image

from vidgen.worker.engines.base import GeneratedVideo


def encode_mp4(video: GeneratedVideo, path: Path, crf: int = 18) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # yuv420p + faststart: plays in every browser and starts before fully downloaded.
    writer = imageio.get_writer(
        path,
        fps=video.fps,
        codec="libx264",
        pixelformat="yuv420p",
        macro_block_size=16,
        ffmpeg_params=["-crf", str(crf), "-movflags", "+faststart"],
    )
    try:
        for frame in video.frames:
            writer.append_data(frame)
    finally:
        writer.close()


def save_thumbnail(video: GeneratedVideo, path: Path, max_side: int = 512) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(video.frames[len(video.frames) // 2])
    image.thumbnail((max_side, max_side))
    image.save(path, format="JPEG", quality=85)
