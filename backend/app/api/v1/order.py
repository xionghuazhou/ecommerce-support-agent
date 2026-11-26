# backend/app/api/v1/order.py
"""订单服务接口"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Order
from app.schemas.business import OrderInfo
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get('/list', response_model=List[OrderInfo])
async def list_orders(user_id: int = Query(1, description='用户ID'),
                      db: AsyncSession = Depends(get_db)):
    """用户订单列表（演示默认 demo 用户）"""
    result = await db.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    )
    return result.scalars().all()


@router.get('/{order_no}', response_model=OrderInfo)
async def get_order(order_no: str, db: AsyncSession = Depends(get_db)):
    """订单详情"""
    result = await db.execute(select(Order).where(Order.order_no == order_no.upper()))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail='订单不存在')
    return order
