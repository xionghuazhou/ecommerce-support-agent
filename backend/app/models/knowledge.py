# backend/app/models/knowledge.py
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Knowledge(Base):
    """知识库表"""
    __tablename__ = 'knowledge'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment='知识分类')
    question: Mapped[str] = mapped_column(Text, nullable=False, comment='问题')
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment='答案')
    keywords: Mapped[str | None] = mapped_column(String(500), comment='关键词，逗号分隔')
    vector_id: Mapped[str | None] = mapped_column(String(100), comment='向量库ID')
    embedding_model: Mapped[str] = mapped_column(String(50), default='BAAI/bge-m3', comment='向量化模型')
    hit_count: Mapped[int] = mapped_column(Integer, default=0, comment='命中次数')
    satisfaction_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), comment='满意度')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否启用')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(),
                                                 onupdate=func.current_timestamp())
