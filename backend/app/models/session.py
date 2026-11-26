# backend/app/models/session.py
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Session(Base):
    """会话表"""
    __tablename__ = 'sessions'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment='会话唯一标识')
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey('users.id'), nullable=False, comment='用户ID')
    agent_id: Mapped[str | None] = mapped_column(String(64), comment='分配的Agent ID')
    status: Mapped[str] = mapped_column(String(20), default='active',
                                        comment='会话状态 active/waiting/transferred/closed')
    channel: Mapped[str] = mapped_column(String(20), default='web', comment='来源渠道')
    satisfaction_score: Mapped[int | None] = mapped_column(Integer, comment='满意度评分 1-5')
    satisfaction_comment: Mapped[str | None] = mapped_column(String(500), comment='评价内容')
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, comment='结束时间')
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, comment='最后消息时间')
    message_count: Mapped[int] = mapped_column(Integer, default=0, comment='消息数量')
