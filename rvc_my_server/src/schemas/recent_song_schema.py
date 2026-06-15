from pydantic import BaseModel, Field


class AddRecentSongRequest(BaseModel):
    songId: str = Field(..., min_length=1)
