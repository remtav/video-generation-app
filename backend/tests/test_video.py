from pathlib import Path

import imageio_ffmpeg
from PIL import Image

from vidgen.db.models import JobMode
from vidgen.worker.engines import GenerationRequest
from vidgen.worker.engines.fake import FakeEngine
from vidgen.worker.video import encode_mp4, save_thumbnail


def test_encode_mp4_and_thumbnail(tmp_path: Path) -> None:
    req = GenerationRequest(
        mode=JobMode.T2V, prompt="x", width=128, height=96, num_frames=17, steps=1, seed=0
    )
    video = FakeEngine().generate(req, lambda *_: None)

    mp4 = tmp_path / "out" / "video.mp4"
    encode_mp4(video, mp4)
    meta = next(imageio_ffmpeg.read_frames(str(mp4)))
    assert meta["fps"] == 24
    assert meta["size"] == (128, 96)
    assert imageio_ffmpeg.count_frames_and_secs(str(mp4))[0] == 17

    thumb = tmp_path / "out" / "thumb.jpg"
    save_thumbnail(video, thumb, max_side=64)
    with Image.open(thumb) as img:
        assert img.size == (64, 48)
