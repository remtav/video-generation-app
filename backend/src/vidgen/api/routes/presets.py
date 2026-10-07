from fastapi import APIRouter

from vidgen.api.schemas import PresetOut
from vidgen.presets import FPS, PRESETS

router = APIRouter(tags=["presets"])


@router.get("/presets", response_model=list[PresetOut])
async def list_presets() -> list[PresetOut]:
    return [PresetOut.from_preset(p, FPS) for p in PRESETS.values()]
