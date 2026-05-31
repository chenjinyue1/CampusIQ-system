import asyncio
import time

from app.models.factory import ChatModelFactory, EmbedModelFactory, VisionModelFactory
from app.rag.reorder_service import check_and_download_reranker_model, ReorderService
from app.services.note_service import NoteService
from app.utils.logger_handler import logger

class _BackgroundInitManager:
    """
    后台初始化管理器
    """
    def __init__(self):
        """初始化后台初始化管理器"""
        self._started = False # 是否已启动, 用于防止重复启动
        self._start_time = 0.0 # 启动时间

        # 各组件的初始化状态事件
        self.models_ready = asyncio.Event() # 模型准备就绪事件, 用于等待模型准备就绪, 然后启动后台初始化, 防止模型未就绪, 导致后台初始化失败, 从而导致程序退出
        self.note_service_ready = asyncio.Event() # 笔记服务准备就绪事件, 用于等待笔记服务准备就绪, 然后启动后台初始化,  prevent note service not ready, cause program exit
        self.reranker_ready = asyncio.Event() # reranker 准备就绪事件, 用于等待 reranker 准备就绪, 然后启动后台初始化,  prevent reranker not ready, cause program exit

        # 初始化后的实例（初始化完成前为 None）
        self.chat_model = None
        self.embed_model = None
        self.vision_model = None # 视觉大模型, 用于看图说话
        self.note_service = None
        self.reorder_service = None # RAG 检索服务, 用于对检索结果进行排序

    async def start(self):
        """启动后台初始化（不阻塞主事件循环）"""
        if self._started:
            return
        self._started = True
        self._start_time = time.time()
        asyncio.create_task(self._initialize_all()) # 创建一个异步任务，用于后台初始化

    async def _initialize_all(self):
        """后台执行所有重型初始化"""
        try:
            logger.info("🔄 开始后台初始化...")

            # 1. AI 模型（调用 factory 中的工厂类）
            await self._init_models()

            # 2. ChromaDB（NoteService，依赖 embed_model）
            await self._init_note_service()

            # 3. 重排序模型（引入 torch、sentence_transformers 等重型框架）
            await self._init_reranker()

            elapsed = time.time() - self._start_time
            logger.info(f"✅ 后台初始化完成，耗时 {elapsed:.1f} 秒")

        except Exception as e:
            logger.error(f"❌ 后台初始化失败：{e}", exc_info=True) # 打印错误信息,exc_info=True, 表示打印错误信息及错误堆栈

    async def _init_models(self):
        """初始化 AI 模型"""
        self.chat_model = await asyncio.to_thread(
            lambda : ChatModelFactory().generator()
        )
        logger.info("✅ chat_model 初始化完成")

        self.embed_model = await asyncio.to_thread(
            lambda : EmbedModelFactory().generator()
        )
        logger.info("✅ embed_model 模型初始化完成")

        self.vision_model = await asyncio.to_thread(
            lambda : VisionModelFactory().generator()
        )
        logger.info("✅ vision_model 模型初始化完成")

        self.models_ready.set() # 设置模型准备就绪事件, 用于等待模型准备就绪, 然后启动后台初始化,

    async def _init_note_service(self):
        """初始化 NoteService（ChromaDB，依赖 embed_model）"""
        await self.models_ready.wait() # 等待模型准备就绪

        self.note_service = await asyncio.to_thread(
            lambda : NoteService(embed_model=self.embed_model)
        )
        logger.info("✅ NoteService（ChromaDB）初始化完成")
        self.note_service_ready.set()

    async def _init_reranker(self):

        await asyncio.to_thread(check_and_download_reranker_model)
        logger.info("✅ 重排序模型检查完成")

        self.reorder_service = ReorderService()
        logger.info("✅ReorderService 初始化完成")
        self.reranker_ready.set()


# 全局单例
init_manager = _BackgroundInitManager()
























