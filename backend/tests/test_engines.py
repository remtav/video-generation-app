import pytest
from PIL import Image

from vidgen.config import Settings
from vidgen.db.models import JobMode
from vidgen.worker.engines import GenerationRequest, create_engine
from vidgen.worker.engines.fake import FakeEngine


def make_request(**overrides: object) -> GenerationRequest:
    params: dict[str, object] = {
        "mode": JobMode.T2V,
        "prompt": "a test",
        "width": 64,
        "height": 32,
        "num_frames": 9,
        "steps": 3,
        "seed": 1,
    }
    params.update(overrides)
    return GenerationRequest(**params)  # type: ignore[arg-type]


def test_fake_engine_output_shape_and_progress() -> None:
    progress: list[tuple[int, int]] = []
    video = FakeEngine().generate(
        make_request(), lambda done, total: progress.append((done, total))
    )
    assert video.frames.shape == (9, 32, 64, 3)
    assert video.frames.dtype.name == "uint8"
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert video.duration_s == pytest.approx(9 / 24)


def test_fake_engine_is_deterministic_per_seed() -> None:
    engine = FakeEngine()
    a = engine.generate(make_request(seed=7), lambda *_: None)
    b = engine.generate(make_request(seed=7), lambda *_: None)
    c = engine.generate(make_request(seed=8), lambda *_: None)
    assert (a.frames == b.frames).all()
    assert not (a.frames == c.frames).all()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"width": 65}, "multiples of 32"),
        ({"num_frames": 10}, "4k\\+1"),
        ({"steps": 0}, "at least 1"),
        ({"mode": JobMode.I2V}, "requires an input image"),
    ],
)
def test_request_validation(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        make_request(**overrides)


def test_i2v_request_with_image() -> None:
    req = make_request(mode=JobMode.I2V, image=Image.new("RGB", (64, 32)))
    assert req.image is not None


def test_registry() -> None:
    assert create_engine(Settings(engine="fake")).name == "fake"
    with pytest.raises(NotImplementedError):
        create_engine(Settings(engine="wan"))
