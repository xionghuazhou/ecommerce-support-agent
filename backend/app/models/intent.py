# backend/app/models/intent.py
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Intent(Base):
    """意图表"""
    __tablename__ = 'intents'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    intent_name: Mapped[str] = mapped_column(String(100), nullable=False, comment='意图名称')
    intent_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment='意图编码')
    description: Mapped[str | None] = mapped_column(String(255), comment='意图描述')
    handler_type: Mapped[str] = mapped_column(String(20), nullable=False,
                                              comment='处理类型 rag/tool/transfer/llm/fallback')
    handler_config: Mapped[dict | None] = mapped_column(JSON, comment='处理配置（默认工具等）')
    sample_utterances: Mapped[str | None] = mapped_column(Text, comment='示例语料，分号分隔（用于语义匹配）')
    priority: Mapped[int] = mapped_column(Integer, default=0, comment='优先级，越高越优先')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否启用')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(),
                                                 onupdate=func.current_timestamp())
