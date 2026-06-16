from pydantic import BaseModel, Field


class AddRecentModelRequest(BaseModel):
    rvcModelId: str = Field(..., min_length=1)
