from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.db_config import close_db
from app.utils.logger_handler import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    在应用启动和关闭时执行初始化和清理操作
    """
    # 启动时的操作
    logger.info("【应用】应用启动中...")

    yield

    # 关闭时的操作
    logger.info("【应用】应用正在关闭...")
    await close_db()
    logger.info("【应用】应用已关闭")
