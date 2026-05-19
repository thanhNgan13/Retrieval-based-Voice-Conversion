from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=80,
        examples=["admin"],
    )
    password: str = Field(
        min_length=1,
        max_length=128,
        examples=["admin"],
    )


class AdminRefreshTokenRequest(BaseModel):
    refreshToken: str = Field(
        min_length=10,
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<payload>.<signature>"],
        description="Refresh token nhận được từ /admin-services/login.",
    )
