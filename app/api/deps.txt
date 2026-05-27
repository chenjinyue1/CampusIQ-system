"""
FastAPI 依赖注入（Depends）。
"""

from typing import Any, AsyncGenerator

import aiomysql
from aiomysql import Connection
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.core.exceptions import unauthorized
from app.core.security import decode_access_token
from app.db.mysql import get_mysql_pool
from app.db.redis_client import get_redis
from app.services import auth_service

# Bearer Token 提取器：从 Header Authorization: Bearer <token> 读取
bearer_scheme = HTTPBearer(auto_error=False)


def get_config() -> Settings:
    """注入全局配置。"""
    return get_settings()


async def get_db() -> AsyncGenerator[Connection, None]:
    """
    注入 MySQL 连接（每个请求从池中借一条）。

    正常结束自动 commit；异常自动 rollback，连接归还池。
    """
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


def get_redis_client() -> Redis:
    """注入 Redis 客户端。"""
    return get_redis()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: Connection = Depends(get_db),
) -> dict[str, Any]:
    """
    解析 JWT 并返回当前用户（字典）。

    用法:
        async def upload(..., user: dict = Depends(get_current_user)):
            user_id = user["id"]
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("未提供有效的 Bearer Token")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise unauthorized("Token 无效或已过期")

    user_id = payload.get("sub")
    if user_id is None:
        raise unauthorized("Token 载荷无效")

    user = await auth_service.get_user_by_id(conn, int(user_id))
    if user is None:
        raise unauthorized("用户不存在")
    if not user.get("is_active"):
        raise unauthorized("用户已被禁用")

    return user
