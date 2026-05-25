"""
Redis 异步客户端。

作用：缓存会话上下文、热门问答等（后续模块使用）。
使用 redis-py 的 asyncio 支持，与 FastAPI 全异步架构一致。
"""

from __future__ import annotations

import time
from typing import Any

from redis.asyncio import Redis

from app.config import Settings

_client: Redis | None = None


async def init_redis(settings: Settings) -> Redis:
    """创建 Redis 客户端（应用启动时调用一次）。"""
    global _client
    if _client is not None:
        return _client

    _client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,  # 返回 str 而非 bytes，便于 JSON 序列化
        encoding="utf-8",
    )
    # 启动时立刻 ping，连接失败则快速报错
    await _client.ping()
    return _client


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis() -> Redis:
    """获取已初始化的 Redis 客户端。"""
    if _client is None:
        raise RuntimeError("Redis 未初始化，请检查 lifespan 是否已执行 init_redis")
    return _client


async def ping_redis() -> dict[str, Any]:
    """健康检查：PING，返回状态与耗时。"""
    start = time.perf_counter()
    try:
        client = get_redis()
        pong = await client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if pong is True or pong == "PONG":
            return {"status": "up", "latency_ms": latency_ms}
        return {"status": "down", "error": f"unexpected pong: {pong}"}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "down", "latency_ms": latency_ms, "error": str(exc)}
