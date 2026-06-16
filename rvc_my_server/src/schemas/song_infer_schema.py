from typing import Annotated

from pydantic import BaseModel, Field


class CreateSongInferFromSongIdRequest(BaseModel):
    songId: str = Field(..., description="ID bài hát cần infer")
    rvcModelId: str = Field(..., description="ID RVC model giọng đích")

    # Separation
    separationDenoise: bool = True
    separationKeepLocal: bool = False

    # Infer
    privateOnly: bool = False
    speakerId: Annotated[int, Field(ge=0)] = 0
    f0UpKey: Annotated[int, Field(ge=-24, le=24)] = 0
    f0Method: str = "rmvpe"
    indexRate: Annotated[float, Field(ge=0.0, le=1.0)] = 0.75
    filterRadius: Annotated[int, Field(ge=0, le=7)] = 3
    resampleSr: Annotated[int, Field(ge=0, le=48000)] = 0
    rmsMixRate: Annotated[float, Field(ge=0.0, le=1.0)] = 0.25
    protect: Annotated[float, Field(ge=0.0, le=0.5)] = 0.33

    # Mixing
    reverbRoomSize: Annotated[float, Field(ge=0.0, le=1.0)] = 0.15
    reverbWetLevel: Annotated[float, Field(ge=0.0, le=1.0)] = 0.20
    reverbDryLevel: Annotated[float, Field(ge=0.0, le=1.0)] = 0.80
    reverbDamping: Annotated[float, Field(ge=0.0, le=1.0)] = 0.70
    mainGain: float = 0.0
    backupGain: float = 0.0
    instGain: float = 0.0
    outputFormat: str = "wav"
    mixingKeepLocal: bool = False
