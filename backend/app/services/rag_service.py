# backend/app/services/rag_service.py
"""RAG 服务：知识库向量化 + 余弦相似度检索（简化版：numpy 代替 Milvus）"""
import asyncio
import json
from typing import List, Dict, Any, Optional

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, DATA_DIR
from app.models.knowledge import Knowledge
from app.services.embedding_service import embedding_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

VECTOR_INDEX_FILE = DATA_DIR / 'vector_index.json'


class RAGService:
    """RAG 检索服务"""

    def __init__(self):
        self._matrix: np.ndarray | None = None
        self._items: List[Dict[str, Any]] = []  # [{id, question, answer, category, keywords}]
        self._loaded = False

    async def load_index(self, db: AsyncSession, force: bool = False):
        """加载知识库并构建向量索引（含缺失向量的补算与持久化）"""
        if self._loaded and not force:
            return

        result = await db.execute(select(Knowledge).where(Knowledge.is_active == True))  # noqa: E712
        rows = result.scalars().all()
        self._items = [
            {'id': r.id, 'question': r.question, 'answer': r.answer,
             'category': r.category, 'keywords': r.keywords or ''}
            for r in rows
        ]

        if not self._items:
            logger.warning('知识库为空，请先运行 scripts/import_knowledge.py')
            self._loaded = True
            return

        texts = [f"{it['question']} {it['keywords']}" for it in self._items]
        self._matrix = await embedding_service.embed(texts)
        self._loaded = True
        await self._persist_index()
        logger.info(f'RAG 索引就绪: {len(self._items)} 条知识, 维度 {self._matrix.shape[1]}, '
                    f'API降级模式={embedding_service.api_failed}')

    async def reload(self, db: AsyncSession):
        """知识库变更后重建索引"""
        self._loaded = False
        await self.load_index(db, force=True)

    async def _persist_index(self):
        """把向量索引持久化到本地（重启时热加载省一次 API 调用）"""
        try:
            payload = {
                'model': settings.EMBEDDING_MODEL,
                'api_failed': embedding_service.api_failed,
                'ids': [it['id'] for it in self._items],
                'items': self._items,
            }
            VECTOR_INDEX_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            np.save(DATA_DIR / 'vector_matrix.npy', self._matrix)
        except Exception as e:
            logger.warning(f'向量索引持久化失败（不影响运行）: {e}')

    async def search(self, query: str, top_k: Optional[int] = None,
                     threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """语义检索知识库，返回 [{...知识字段, score}]，按相似度降序"""
        if self._matrix is None or not len(self._items):
            return []

        top_k = top_k or settings.RAG_TOP_K
        threshold = threshold if threshold is not None else settings.RAG_SIMILARITY_THRESHOLD

        query_vec = await embedding_service.embed_one(query)
        sims = self._matrix @ query_vec
        order = np.argsort(sims)[::-1][:top_k]

        results = []
        for idx in order:
            score = float(sims[idx])
            if score < threshold:
                continue
            item = {**self._items[int(idx)], 'score': round(score, 4)}
            results.append(item)
        return results

    async def increment_hit_count(self, db: AsyncSession, knowledge_ids: List[int]):
        """更新命中次数"""
        if knowledge_ids:
            await db.execute(
                update(Knowledge).where(Knowledge.id.in_(knowledge_ids)),
                {'hit_count': Knowledge.hit_count + 1}
            )
            await db.commit()


# 全局单例
rag_service = RAGService()
