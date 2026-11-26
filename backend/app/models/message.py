# backend/app/models/message.py
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Message(Base):
    """消息表"""
    __tablename__ = 'messages'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    session_row_id: Mapped[int] = mapped_column(BigInt, ForeignKey('sessions.id'), nullable=False,
                                                comment='会话自增ID')
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='会话唯一标识')
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False, comment='发送者类型 user/bot/agent')
    sender_id: Mapped[int | None] = mapped_column(BigInt, comment='发送者ID')
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='消息内容')
    content_type: Mapped[str] = mapped_column(String(20), default='text',
                                              comment='内容类型 text/image/voice/file/quick_reply')
    intent_code: Mapped[str | None] = mapped_column(String(50), comment='识别的意图编码')
    intent_name: Mapped[str | None] = mapped_column(String(100), comment='意图名称')
    intent_confidence: Mapped[float | None] = mapped_column(comment='意图置信度')
    sentiment: Mapped[str | None] = mapped_column(String(20), comment='情感倾向 positive/neutral/negative')
    sentiment_score: Mapped[float | None] = mapped_column(comment='情感得分 -1.0 ~ 1.0')
    is_human_transfer: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否转人工')
    is_generated: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否AI生成')
    meta_data: Mapped[dict | None] = mapped_column(JSON, comment='元数据（工具调用轨迹等）')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
