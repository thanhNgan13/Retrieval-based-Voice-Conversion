from typing import Optional

from pydantic import BaseModel, Field


class UpdateRvcModelRequest(BaseModel):
    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=120,
        examples=["Giọng nam ấm áp"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        examples=["Giọng nam trầm, phù hợp đọc sách nói."],
    )
