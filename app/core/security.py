"""
JWT 与密码安全工具。

作用：
- 密码用 bcrypt 哈希存储（数据库里绝不存明文）
- 登录成功后签发 JWT，后续请求带 Token 识别用户

说明：直接使用 bcrypt 库，避免 passlib 与 bcrypt 5.x 不兼容导致登录 500/400。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings


def hash_password(plain_password: str) -> str:
    """注册时将明文密码转为哈希存入数据库。"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """登录时比对用户输入与数据库哈希。"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    生成 JWT Access Token。

    data 一般包含 sub（用户ID）、username 等，不包含密码。
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": int(expire.timestamp())})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    解析并校验 Token，失败返回 None（由调用方决定是否抛 401）。
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None
