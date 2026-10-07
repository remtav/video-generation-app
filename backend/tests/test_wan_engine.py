"""WanEngine against a tiny random Wan 2.2 TI2V-5B-shaped pipeline on the CPU.

The components mirror diffusers' own Wan 2.2 5B tests (z_dim 48 VAE with patch size 2 and
16x spatial compression, expand_timesteps transformer, UniPC flow scheduler, UMT5 encoder),
so this exercises the real diffusers code paths the worker uses, without a GPU or weights.

Needs the ``cpu`` extra (``uv sync --extra cpu``); skipped otherwise.
"""

from typing import Any

import numpy as np
import pytest

torch = pytest.importorskip("torch")
diffusers = pytest.importorskip("diffusers")
transformers = pytest.importorskip("transformers")

from vidgen.db.models import JobMode  # noqa: E402
from vidgen.worker.engines import (  # noqa: E402
    EngineOutOfMemory,
    GenerationCancelled,
    GenerationRequest,
)
from vidgen.worker.engines.wan import WanEngine  # noqa: E402

TINY_TOKENIZER = "hf-internal-testing/tiny-random-t5"


def tiny_pipeline() -> Any:
    from diffusers import (
        AutoencoderKLWan,
        UniPCMultistepScheduler,
        WanPipeline,
        WanTransformer3DModel,
    )
    from transformers import AutoConfig, AutoTokenizer, UMT5Config, UMT5EncoderModel

    torch.manual_seed(0)
    vae = AutoencoderKLWan(
        base_dim=3,
        z_dim=48,
        in_channels=12,
        out_channels=12,
        is_residual=True,
        patch_size=2,
        latents_mean=[0.0] * 48,
        latents_std=[1.0] * 48,
        dim_mult=[1, 1, 1, 1],
        num_res_blocks=1,
        scale_factor_spatial=16,
        scale_factor_temporal=4,
        temperal_downsample=[False, True, True],
    )
    scheduler = UniPCMultistepScheduler(
        prediction_type="flow_prediction", use_flow_sigmas=True, flow_shift=5.0
    )
    t5 = AutoConfig.from_pretrained(TINY_TOKENIZER)
    text_encoder = UMT5EncoderModel(
        UMT5Config(
            vocab_size=t5.vocab_size,
            d_model=t5.d_model,
            d_kv=t5.d_kv,
            d_ff=t5.d_ff,
            num_layers=t5.num_layers,
            num_heads=t5.num_heads,
            relative_attention_num_buckets=t5.relative_attention_num_buckets,
            pad_token_id=t5.pad_token_id,
            eos_token_id=t5.eos_token_id,
        )
    ).eval()
    transformer = WanTransformer3DModel(
        patch_size=(1, 2, 2),
        num_attention_heads=2,
        attention_head_dim=12,
        in_channels=48,
        out_channels=48,
        text_dim=t5.d_model,
        freq_dim=256,
        ffn_dim=32,
        num_layers=2,
        cross_attn_norm=True,
        qk_norm="rms_norm_across_heads",
        rope_max_seq_len=32,
        image_dim=None,
    )
    return WanPipeline(
        transformer=transformer,
        vae=vae,
        scheduler=scheduler,
        text_encoder=text_encoder,
        tokenizer=AutoTokenizer.from_pretrained(TINY_TOKENIZER),
        transformer_2=None,
        boundary_ratio=None,
        expand_timesteps=True,
    )


@pytest.fixture(scope="module")
def engine() -> WanEngine:
    engine = WanEngine("tiny", vae_tiling=True, pipeline_factory=tiny_pipeline)
    engine.load()
    return engine


def request(**overrides: Any) -> GenerationRequest:
    params: dict[str, Any] = {
        "mode": JobMode.T2V,
        "prompt": "a cat surfing",
        "negative_prompt": "blurry",
        "width": 64,
        "height": 32,
        "num_frames": 9,
        "steps": 3,
        "seed": 1,
    }
    params.update(overrides)
    return GenerationRequest(**params)


def test_generate_returns_uint8_frames_and_reports_each_step(engine: WanEngine) -> None:
    progress: list[tuple[int, int]] = []
    video = engine.generate(request(), lambda done, total: progress.append((done, total)))
    assert video.frames.shape == (9, 32, 64, 3)
    assert video.frames.dtype == np.uint8
    assert video.fps == 24
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_same_seed_is_reproducible(engine: WanEngine) -> None:
    a = engine.generate(request(seed=5), lambda *_: None)
    b = engine.generate(request(seed=5), lambda *_: None)
    c = engine.generate(request(seed=6), lambda *_: None)
    assert np.array_equal(a.frames, b.frames)
    assert not np.array_equal(a.frames, c.frames)


def test_cancel_from_callback_stops_run_and_engine_stays_usable(engine: WanEngine) -> None:
    calls: list[int] = []

    def cancel_at_second_step(done: int, total: int) -> None:
        calls.append(done)
        if done == 2:
            raise GenerationCancelled

    with pytest.raises(GenerationCancelled):
        engine.generate(request(steps=5), cancel_at_second_step)
    assert calls == [1, 2]

    after = engine.generate(request(seed=5), lambda *_: None)
    again = engine.generate(request(seed=5), lambda *_: None)
    assert np.array_equal(after.frames, again.frames)


def test_out_of_memory_is_translated() -> None:
    class OomPipeline:
        vae = type("Vae", (), {"enable_tiling": lambda self: None})()
        freed = False

        def to(self, device: str) -> None:
            pass

        def set_progress_bar_config(self, **kwargs: Any) -> None:
            pass

        def maybe_free_model_hooks(self) -> None:
            OomPipeline.freed = True

        def __call__(self, **kwargs: Any) -> Any:
            raise torch.OutOfMemoryError("CUDA out of memory")

    engine = WanEngine("x", pipeline_factory=OomPipeline)
    engine.load()
    with pytest.raises(EngineOutOfMemory):
        engine.generate(request(), lambda *_: None)
    assert OomPipeline.freed


def test_generate_before_load_fails() -> None:
    with pytest.raises(RuntimeError, match="load"):
        WanEngine("x", pipeline_factory=tiny_pipeline).generate(request(), lambda *_: None)
