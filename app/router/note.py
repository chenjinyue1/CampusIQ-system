"""
笔记管理 API 路由 —— CRUD、搜索、自动标签、内联补全、写作辅助。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.background_init import init_manager
from app.core.rate_limit import rate_limit
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.schemas.models import NoteCreate
from app.services.auth_utils import get_current_user_id

note_router = APIRouter(prefix="/note", tags=["note"])

@note_router.post("/create")
async def create_note(
        payload: NoteCreate, # 笔记创建请求模型，用于创建笔记
        user_id : str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        _: None = Depends(rate_limit(limit=10, window=60)) # 限流, 限制用户每分钟最多创建 10 个笔记, 防止用户滥用
):
    """
    创建笔记：
    1. MySQL 写入 + ChromaDB 向量化
    2. 立即返回笔记（tags/category 初始为空）
    3. 后台异步生成标签和回顾记录
    """
    note = await init_manager.note_service.create_note(db, user_id, payload)
    return success_response(message="笔记创建成功", data=note)






