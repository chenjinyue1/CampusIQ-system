import time
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware

from app.core.failed_response_register import register_exception_handlers
from app.db.db_config import init_db, close_db
from app.db.redis_config import connect_redis, close_redis
from app.services.database_session_manager import init_database_session_manager
from app.utils.logger_handler import logger
from app.core.rate_limit import RateLimitMiddleware

from app.router.health import health_router
from app.router.user import user_router
from app.router.knowledge import knowledge_router


# 加载环境变量
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时的操作
    logger.info("【应用】开始初始化...")

    # 初始化数据库表结构
    await init_db()
    logger.info("数据库表结构初始化完成")

    # 使用数据库版本的会话管理器
    await init_database_session_manager()
    logger.info("数据库会话管理器初始化完成")

    # 连接Redis
    await connect_redis()
    logger.info("Redis连接初始化完成")

    # # 检查并重排序模型
    # check_and_download_reranker_model()
    # logger.info("重排序模型检查完成")

    yield

    # 关闭时的操作
    logger.info("【应用】开始清理资源...")
    await close_redis()
    logger.info("Redis连接已关闭")
    await close_db()
    logger.info("数据库连接已关闭")

app = FastAPI(lifespan=lifespan)



# 集成限流中间件（暂时注释掉，以免在调试阶段干扰正常请求）
# RateLimitMiddleware 基于令牌桶实现，每 60 秒允许 100 个请求
# 正式部署时可根据接口负载调整限流策略
# 所有限流（包括路由上的 Depends(rate_limit(...))）通过 RATE_LIMIT_ENABLED=false 一键关闭
# app.add_middleware(RateLimitMiddleware, limit=100, window=60)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time, 4))
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 允许访问的源
    allow_credentials=True, # 允许携带cookie
    allow_methods=["*"], # 允许的请求方法
    allow_headers=["*"], # 允许的请求头
)

# 注册异常处理函数
register_exception_handlers(app)



@app.get('/')
async def root():
    return {'message': 'Hello World'}


@app.get('/hellow/{name}')
async def hello(name: str):
    return {'message': f'Hello {name}'}


app.include_router(health_router)
app.include_router(user_router)
app.include_router(knowledge_router)



# 测试路由
if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
