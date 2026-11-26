# backend/app/models/user.py
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class User(Base):
    """用户表"""
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment='用户名')
    email: Mapped[str | None] = mapped_column(String(100), unique=True, comment='邮箱')
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, comment='手机号')
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default='', comment='密码哈希')
    user_type: Mapped[str] = mapped_column(String(20), default='customer', comment='用户类型 customer/agent/admin')
    avatar_url: Mapped[str | None] = mapped_column(String(500), comment='头像URL')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否激活')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(),
                                                onupdate=func.current_timestamp())
