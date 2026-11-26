# backend/app/core/config.py
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 项目根目录：backend/app/core/config.py -> 上溯 3 级
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / 'data'
KNOWLEDGE_BASE_FILE = PROJECT_ROOT / 'knowledge_base' / 'faqs.json'
FRONTEND_STATIC_DIR = PROJECT_ROOT / 'frontend' / 'static'

DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_ROOT / '.env')


class Settings(BaseSettings):
    """应用配置（从项目根目录 .env 读取）"""
    model_config = SettingsConfigDict(extra='ignore')

    PROJECT_NAME: str = '电商智能客服系统'
    VERSION: str = '1.0.0'

    # 数据库（简化：SQLite 代替 MySQL）
    DATABASE_URL: str = f'sqlite+aiosqlite:///{(DATA_DIR / "customer_service.db").as_posix()}'

    # LLM（OpenAI 兼容接口）
    LLM_API_KEY: str = ''
    LLM_BASE_URL: str = 'https://api.siliconflow.cn/v1'
    LLM_MODEL: str = 'Qwen/Qwen2.5-7B-Instruct'
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 1024

    # Embedding / RAG
    EMBEDDING_MODEL: str = 'BAAI/bge-m3'
    EMBEDDING_DIM: int = 1024
    EMBEDDING_BATCH_SIZE: int = 32
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.5

    # Agent
    AGENT_NAME: str = '小e'
    AGENT_MAX_ITERATIONS: int = 5
    AUTO_TRANSFER_SENTIMENT_THRESHOLD: float = -0.5

    # 意图识别
    INTENT_THRESHOLD: float = 0.6


settings = Settings()
