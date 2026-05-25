"""
MySQL 异步连接池（aiomysql）。

作用：全局维护一个连接池，业务代码通过 get_db() 借连接，用完自动归还。
为什么用连接池：避免每次请求都新建 TCP 连接，是企业高并发下的标准做法。
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import aiomysql
from aiomysql import Connection, DictCursor, Pool

from app.config import Settings

# 模块级单例，在 lifespan 启动时赋值
_pool: Pool | None = None


async def init_mysql_pool(settings: Settings) -> Pool:
    """创建连接池（应用启动时调用一次）。"""
    global _pool
    if _pool is not None:
        return _pool

    _pool = await aiomysql.create_pool(
        minsize=1,
        maxsize=10,
        echo=settings.debug,
        **settings.mysql_dsn,
    )
    return _pool


async def close_mysql_pool() -> None:
    """关闭连接池（应用关闭时调用）。"""
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def get_mysql_pool() -> Pool:
    """获取已初始化的连接池。"""
    if _pool is None:
        raise RuntimeError("MySQL 连接池未初始化，请检查 lifespan 是否已执行 init_mysql_pool")
    return _pool


@asynccontextmanager
async def acquire_connection() -> AsyncGenerator[Connection, None]:
    """
    从池中借一条连接，with 块结束自动归还。

    发生异常时自动 rollback，避免未提交事务占用行锁导致 1205。
    """
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        try:
            yield conn
        except Exception:
            await conn.rollback()
            raise


@asynccontextmanager
async def transaction() -> AsyncGenerator[Connection, None]:
    """
    短事务：成功 commit，失败 rollback。

    用于后台任务等需要尽快释放 MySQL 锁的场景。
    """
    async with acquire_connection() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


async def ping_mysql() -> dict[str, Any]:
    """
    健康检查：执行 SELECT 1，返回状态与耗时（毫秒）。
    """
    start = time.perf_counter()
    try:
        async with acquire_connection() as conn:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute("SELECT 1 AS ok")
                row = await cur.fetchone()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if row and row.get("ok") == 1:
            return {"status": "up", "latency_ms": latency_ms}
        return {"status": "down", "error": "unexpected response"}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "down", "latency_ms": latency_ms, "error": str(exc)}


# ---------- 常用 SQL 辅助（减少 services 层重复代码）----------


async def fetch_one(
    conn: Connection,
    sql: str,
    args: tuple | list | None = None,
) -> dict[str, Any] | None:
    """查询单行，返回字典。"""
    async with conn.cursor(DictCursor) as cur:
        await cur.execute(sql, args or ())
        return await cur.fetchone()


async def fetch_all(
    conn: Connection,
    sql: str,
    args: tuple | list | None = None,
) -> list[dict[str, Any]]:
    """查询多行，返回字典列表。"""
    async with conn.cursor(DictCursor) as cur:
        await cur.execute(sql, args or ())
        return await cur.fetchall()


async def execute(
    conn: Connection,
    sql: str,
    args: tuple | list | None = None,
) -> int:
    """执行 INSERT/UPDATE/DELETE，返回影响行数。"""
    async with conn.cursor() as cur:
        await cur.execute(sql, args or ())
        return cur.rowcount


async def execute_insert(
    conn: Connection,
    sql: str,
    args: tuple | list | None = None,
) -> int:
    """执行 INSERT 并返回自增主键 lastrowid。"""
    async with conn.cursor() as cur:
        await cur.execute(sql, args or ())
        return cur.lastrowid
