# backend/app/api/v1/product.py
"""商品服务接口"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Product
from app.schemas.business import ProductInfo
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get('/list', response_model=List[ProductInfo])
async def list_products(keyword: str = None, category: str = None,
                        db: AsyncSession = Depends(get_db)):
    """商品列表/搜索"""
    stmt = select(Product).where(Product.is_active == True)  # noqa: E712
    if keyword:
        like = f'%{keyword}%'
        stmt = stmt.where(or_(Product.name.like(like), Product.category.like(like),
                              Product.description.like(like)))
    if category:
        stmt = stmt.where(Product.category == category)
    stmt = stmt.order_by(Product.sales.desc()).limit(20)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get('/{product_id}', response_model=ProductInfo)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail='商品不存在')
    return product
