# backend/app/models/product.py
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Numeric, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Product(Base):
    """商品表"""
    __tablename__ = 'products'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment='商品名称')
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment='商品分类')
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, comment='价格')
    description: Mapped[str | None] = mapped_column(Text, comment='商品描述')
    stock: Mapped[int] = mapped_column(Integer, default=0, comment='库存')
    sales: Mapped[int] = mapped_column(Integer, default=0, comment='销量')
    promotion: Mapped[str | None] = mapped_column(String(200), comment='促销活动')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否上架')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
