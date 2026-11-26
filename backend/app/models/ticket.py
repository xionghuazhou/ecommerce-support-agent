# backend/app/models/ticket.py
from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Ticket(Base):
    """工单表"""
    __tablename__ = 'tickets'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment='工单编号')
    session_id: Mapped[str | None] = mapped_column(String(64), comment='关联会话')
    user_id: Mapped[int | None] = mapped_column(BigInt, comment='用户ID')
    type: Mapped[str] = mapped_column(String(30), default='consult', comment='工单类型 complaint/refund/consult/suggestion')
    title: Mapped[str] = mapped_column(String(200), default='用户咨询', comment='工单标题')
    content: Mapped[str] = mapped_column(Text, default='', comment='工单内容')
    status: Mapped[str] = mapped_column(String(20), default='pending', comment='状态 pending/processing/resolved')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
