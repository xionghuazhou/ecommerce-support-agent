# backend/app/agents/tools/query_product.py
from typing import Dict, Any, List

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool
from app.models.product import Product
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class QueryProductTool(BaseTool):
    """商品查询工具"""
    name = 'query_product'
    description = '搜索商品信息、价格、库存'
    parameters = {
        'type': 'object',
        'properties': {
            'keywords': {'type': 'string', 'description': '商品关键词'},
            'category': {'type': 'string', 'description': '商品分类'}
        },
        'required': ['keywords']
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            db: AsyncSession | None = params.get('db')
            if db is None:
                return {'success': False, 'response': '数据库会话不可用', 'data': {}}

            keywords = (params.get('keywords') or '').strip()
            if not keywords:
                return {'success': False, 'response': '请提供商品关键词', 'data': {}}

            # 去掉口语化修饰词，取关键词本体做模糊匹配
            stop_words = ['请问', '一下', '你们', '有没有', '什么', '怎么样', '推荐', '热销', '多少钱']
            cleaned = keywords
            for w in stop_words:
                cleaned = cleaned.replace(w, '')
            cleaned = cleaned.strip() or keywords

            stmt = select(Product).where(Product.is_active == True)  # noqa: E712
            like = f'%{cleaned}%'
            stmt = stmt.where(or_(Product.name.like(like),
                                  Product.category.like(like),
                                  Product.description.like(like)))
            if params.get('category'):
                stmt = stmt.where(Product.category == params['category'])
            stmt = stmt.order_by(Product.sales.desc()).limit(5)

            result = await db.execute(stmt)
            products: List[Product] = result.scalars().all()

            if not products:
                return {
                    'success': True,
                    'response': f'未找到与"{keywords}"相关的商品，可以换个关键词试试，或看看商城热销榜单。',
                    'data': {'products': []}
                }

            lines = []
            for p in products:
                stock_text = f'库存 {p.stock}' if p.stock > 0 else '⚠️ 暂时缺货'
                promo = f'｜🎉 {p.promotion}' if p.promotion else ''
                lines.append(f"🛍️ {p.name}（{p.category}）\n价格：￥{p.price}｜{stock_text}{promo}\n{p.description or ''}")

            return {
                'success': True,
                'response': f'为您找到 {len(products)} 件相关商品：\n\n' + '\n\n'.join(lines),
                'data': {'products': [
                    {'id': p.id, 'name': p.name, 'price': float(p.price), 'stock': p.stock,
                     'promotion': p.promotion} for p in products
                ]}
            }
        except Exception as e:
            logger.error(f'商品查询失败: {e}')
            return {'success': False, 'response': '商品查询出现异常，请稍后重试', 'data': {}}
