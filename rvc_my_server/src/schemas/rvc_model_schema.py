from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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


class DeleteRvcModelsRequest(BaseModel):
    rvc_model_ids: list[str] = Field(
        ...,
        alias="rvcModelIds",
        min_length=1,
        max_length=100,
        description="Danh sách 1-100 rvcModelId cần xoá.",
        examples=[["rvc_model_abc123", "rvc_model_def456"]],
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"rvcModelIds": ["rvc_model_abc123", "rvc_model_def456"]}},
    )
