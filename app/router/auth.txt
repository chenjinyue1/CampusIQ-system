# from fastapi import APIRouter, Depends
# from fastapi.security import HTTPAuthorizationCredentials
#
# from app.core.success_response import success_response
# from app.services.auth_utils import get_current_user_id, security, get_user_info_from_redis
#
# user_router = APIRouter(prefix="/user", tags=["用户"])
#
# @user_router.get("/detail")
# async def get_user_info(user_id: str = Depends(get_current_user_id), credentials: HTTPAuthorizationCredentials = Depends(security)):
#     """获取用户信息"""
#     # 借助 uuid 去查询redis 中存储的用户信息
#     user_info = await get_user_info_from_redis(user_id, credentials)
#     return success_response(
#         message="获取用户信息成功",
#         data=user_info,
#     )

"""
用户认证 API：注册、登录、获取当前用户。
"""

from aiomysql import Connection
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_db
from app.core.exceptions import bad_request
from app.core.security import create_access_token
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services import auth_service


auth_router = APIRouter(prefix="/auth", tags=["用户"])

def _to_user_response(user: dict) -> UserResponse:
    """数据库行 → 响应模型（统一字段映射）。"""
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        is_active=bool(user["is_active"]),
        created_at=user["created_at"],
    )


@auth_router.post("/register", response_model=UserResponse, summary="用户注册")
async def register(body: UserRegisterRequest, conn: Connection = Depends(get_db)):
    """
    注册新用户。

    - 用户名/邮箱不可重复
    - 密码 bcrypt 哈希后入库
    """
    if await auth_service.username_or_email_exists(conn, body.username, body.email):
        raise bad_request("用户名或邮箱已被注册")

    user_id = await auth_service.create_user(
        conn, body.username, body.email, body.password
    )
    user = await auth_service.get_user_by_id(conn, user_id)
    return _to_user_response(user)


@auth_router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login(body: UserLoginRequest, conn: Connection = Depends(get_db)):
    """
    登录校验通过后返回 JWT。

    前端后续请求在 Header 携带: Authorization: Bearer <token>
    """
    user = await auth_service.authenticate_user(conn, body.username, body.password)
    if user is None:
        raise bad_request("用户名或密码错误")

    token = create_access_token(
        data={"sub": str(user["id"]), "username": user["username"]}
    )
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserResponse, summary="获取当前登录用户")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    受保护接口示例：必须携带有效 JWT 才能访问。
    模块3 文档上传等接口将同样使用 Depends(get_current_user)。
    """
    return _to_user_response(current_user)

