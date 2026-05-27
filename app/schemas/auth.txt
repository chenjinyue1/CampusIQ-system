"""认证相关 Pydantic 模型（请求体 / 响应体）。"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """注册请求"""

    username: str = Field(..., min_length=3, max_length=64, description="登录名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class UserLoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class TokenResponse(BaseModel):
    """登录成功返回的 Token"""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """返回给前端的用户信息（不含密码）"""

    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime
