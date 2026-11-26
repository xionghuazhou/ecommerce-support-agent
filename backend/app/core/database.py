# backend/app/core/database.py
from sqlalchemy import BigInteger, Integer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# SQLite 主键自增要求 INTEGER 类型，MySQL 场景仍用 BIGINT（跨库兼容写法）
BigInt = BigInteger().with_variant(Integer, 'sqlite')


class Base(DeclarativeBase):
    """ORM 基类"""
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # timeout: SQLite 忙等超时（秒）。推理模型单条消息处理可达 15-40s，
    # 并发请求写库需等待，避免 "database is locked" 500
    connect_args={'check_same_thread': False, 'timeout': 30},
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI 依赖：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
