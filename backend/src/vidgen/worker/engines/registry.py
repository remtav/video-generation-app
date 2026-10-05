from vidgen.config import Settings
from vidgen.worker.engines.base import VideoEngine
from vidgen.worker.engines.fake import FakeEngine


def create_engine(settings: Settings) -> VideoEngine:
    if settings.engine == "fake":
        return FakeEngine(step_delay=settings.fake_step_delay)
    if settings.engine == "wan":
        # The Wan 2.2 adapter is implemented in Phase 2 (see docs/DEV_PLAN.md).
        raise NotImplementedError("the 'wan' engine is not implemented yet; use 'fake'")
    raise ValueError(f"unknown engine: {settings.engine}")
