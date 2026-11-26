# backend/app/api/v1/knowledge.py
"""知识库管理接口"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Knowledge
from app.schemas.business import KnowledgeCreateRequest, KnowledgeInfo, KnowledgeSearchRequest
from app.services.rag_service import rag_service
from app.services.embedding_service import embedding_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get('/list', response_model=List[KnowledgeInfo])
async def list_knowledge(keyword: str = None, category: str = None,
                         db: AsyncSession = Depends(get_db)):
    """知识列表（支持关键词/分类过滤）"""
    stmt = select(Knowledge)
    if keyword:
        stmt = stmt.where(Knowledge.question.like(f'%{keyword}%'))
    if category:
        stmt = stmt.where(Knowledge.category == category)
    stmt = stmt.order_by(Knowledge.id).limit(100)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post('/create', response_model=KnowledgeInfo)
async def create_knowledge(req: KnowledgeCreateRequest, db: AsyncSession = Depends(get_db)):
    """新增知识（自动向量化并重建索引）"""
    item = Knowledge(category=req.category, question=req.question, answer=req.answer,
                     keywords=req.keywords or '', embedding_model='BAAI/bge-m3')
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await rag_service.reload(db)
    logger.info(f'新增知识 #{item.id}: {req.question[:30]}')
    return item


@router.delete('/{knowledge_id}')
async def delete_knowledge(knowledge_id: int, db: AsyncSession = Depends(get_db)):
    """删除知识（逻辑删除 + 重建索引）"""
    result = await db.execute(select(Knowledge).where(Knowledge.id == knowledge_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail='知识不存在')
    item.is_active = False
    await db.commit()
    await rag_service.reload(db)
    return {'success': True, 'message': f'知识 #{knowledge_id} 已删除'}


@router.post('/search')
async def search_knowledge(req: KnowledgeSearchRequest, db: AsyncSession = Depends(get_db)):
    """语义检索知识库（RAG 演示接口），返回命中条目与相似度"""
    hits = await rag_service.search(req.query, top_k=req.top_k, threshold=0.3)
    return {'query': req.query, 'embedding_mode': 'api' if not embedding_service.api_failed else 'fallback',
            'count': len(hits), 'hits': hits}
