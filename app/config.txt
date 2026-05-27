"""
应用配置模块。

作用：从 .env 读取所有环境变量，集中管理，避免在代码里硬编码。
为什么用 pydantic-settings：启动时自动校验类型，缺配置会立刻报错，符合企业规范。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（app 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置，字段名与 .env 中的 KEY 一一对应。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = Field(default="CampusIQ", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    # 测试时设为 true，跳过 MySQL/Redis 初始化（pytest 使用）
    skip_db_init: bool = Field(default=False, alias="SKIP_DB_INIT")

    # ---------- MySQL ----------
    mysql_host: str = Field(default="127.0.0.1", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="root", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="campusiq", alias="MYSQL_DATABASE")

    # ---------- Redis ----------
    redis_host: str = Field(default="127.0.0.1", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")

    # ---------- JWT ----------
    jwt_secret_key: str = Field(
        default="dev-secret-change-in-production",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=1440, alias="JWT_EXPIRE_MINUTES")

    # ---------- Ollama ----------
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        alias="OLLAMA_BASE_URL",
    )
    ollama_chat_model: str = Field(default="qwen2.5:7b", alias="OLLAMA_CHAT_MODEL")
    ollama_embed_model: str = Field(
        default="qwen3-embedding:4b",
        alias="OLLAMA_EMBED_MODEL",
    )

    # ---------- Chroma ----------
    chroma_persist_dir: str = Field(default="./chroma_data", alias="CHROMA_PERSIST_DIR")
    chroma_collection_name: str = Field(
        default="campusiq_docs",
        alias="CHROMA_COLLECTION_NAME",
    )

    # ---------- RAG ----------
    chunk_size: int = Field(default=500, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=50, alias="CHUNK_OVERLAP")
    separators: list[str] = Field(default=["\n\n", "\n", "。", "！", "？", ".", " ", ""], alias="SEPARATORS")
    rag_top_k: int = Field(default=4, alias="RAG_TOP_K")

    # ---------- Tavily / LangSmith（可选）----------
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="campusiq", alias="LANGCHAIN_PROJECT")

    # ---------- 文件上传 ----------
    upload_dir: str = Field(default="./uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=20, alias="MAX_UPLOAD_SIZE_MB")

    @property
    def mysql_dsn(self) -> dict:
        """aiomysql 连接参数字典，供 db/mysql.py 使用。"""
        return {
            "host": self.mysql_host,
            "port": self.mysql_port,
            "user": self.mysql_user,
            "password": self.mysql_password,
            "db": self.mysql_database,
            "charset": "utf8mb4",
            "autocommit": False,
        }

    @property
    def redis_url(self) -> str:
        """Redis 连接 URL。"""
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}"
                f"@{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def upload_path(self) -> Path:
        """上传目录绝对路径，不存在则自动创建。"""
        path = BASE_DIR / self.upload_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chroma_path(self) -> Path:
        """Chroma 持久化目录。"""
        path = BASE_DIR / self.chroma_persist_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """
    单例获取配置（lru_cache 保证全局只读一次 .env）。
    在 FastAPI 里通过 Depends(get_settings) 注入。
    """
    return Settings()
