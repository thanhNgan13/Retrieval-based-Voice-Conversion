from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr = Field(examples=["ngan@dut.edu.vn"])
    password: str = Field(
        min_length=6,
        max_length=128,
        examples=["Abc12345"],
        description="Mật khẩu từ 6 đến 128 ký tự.",
    )
    name: str = Field(
        min_length=1,
        max_length=80,
        examples=["Phan Thanh Ngan"],
    )


class LoginRequest(BaseModel):
    email: EmailStr = Field(examples=["ngan@dut.edu.vn"])
    password: str = Field(
        min_length=1,
        max_length=128,
        examples=["Abc12345"],
    )


class RefreshTokenRequest(BaseModel):
    refreshToken: str = Field(
        min_length=10,
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.<payload>.<signature>"],
        description="Refresh token nhận được khi đăng nhập hoặc đăng ký.",
    )
