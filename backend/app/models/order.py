# backend/app/models/order.py
from datetime import datetime

from sqlalchemy import String, DateTime, Numeric, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, BigInt


class Order(Base):
    """订单表"""
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey('users.id'), nullable=False, comment='用户ID')
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment='订单号')
    status: Mapped[str] = mapped_column(String(20), default='pending_payment',
                                        comment='状态 pending_payment/paid/shipped/delivered/completed/cancelled/refunding/refunded')
    product_name: Mapped[str] = mapped_column(String(200), nullable=False, comment='商品名称')
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment='数量')
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, comment='订单金额')
    payment_method: Mapped[str | None] = mapped_column(String(30), comment='支付方式')
    tracking_no: Mapped[str | None] = mapped_column(String(64), comment='物流单号')
    shipping_company: Mapped[str | None] = mapped_column(String(30), comment='物流公司')
    receiver_name: Mapped[str | None] = mapped_column(String(50), comment='收货人')
    receiver_address: Mapped[str | None] = mapped_column(String(300), comment='收货地址')
    remark: Mapped[str | None] = mapped_column(String(300), comment='备注')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(),
                                                 onupdate=func.current_timestamp())
