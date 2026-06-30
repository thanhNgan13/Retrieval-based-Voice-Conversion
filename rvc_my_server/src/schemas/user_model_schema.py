from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UpdateUserModelRequest(BaseModel):
    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=120,
        examples=["Giọng tôi"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        examples=["Model giọng nói cá nhân."],
    )

    model_config = ConfigDict(populate_by_name=True)
