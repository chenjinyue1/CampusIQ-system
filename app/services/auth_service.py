"""
用户认证业务逻辑。

作用：封装 SQL 与密码校验，api 层只负责接收参数和返回响应。
"""

from typing import Any

from aiomysql import Connection

from app.core.security import hash_password, verify_password
from app.db.mysql import execute_insert, fetch_one


async def get_user_by_username(conn: Connection, username: str) -> dict[str, Any] | None:
    return await fetch_one(
        conn,
        "SELECT id, username, email, hashed_password, is_active, created_at "
        "FROM users WHERE username = %s",
        (username,),
    )


async def get_user_by_id(conn: Connection, user_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        conn,
        "SELECT id, username, email, is_active, created_at "
        "FROM users WHERE id = %s",
        (user_id,),
    )


async def username_or_email_exists(
    conn: Connection,
    username: str,
    email: str,
) -> bool:
    row = await fetch_one(
        conn,
        "SELECT id FROM users WHERE username = %s OR email = %s LIMIT 1",
        (username, email),
    )
    return row is not None


async def create_user(
    conn: Connection,
    username: str,
    email: str,
    password: str,
) -> int:
    """注册新用户，返回 user_id。"""
    hashed = hash_password(password)
    user_id = await execute_insert(
        conn,
        "INSERT INTO users (username, email, hashed_password) VALUES (%s, %s, %s)",
        (username, email, hashed),
    )
    return user_id


async def authenticate_user(
    conn: Connection,
    username: str,
    password: str,
) -> dict[str, Any] | None:
    """
    校验用户名密码。
    成功返回用户字典（含 id）；失败返回 None。
    """
    user = await get_user_by_username(conn, username)
    if user is None:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    if not user.get("is_active"):
        return None
    return user
