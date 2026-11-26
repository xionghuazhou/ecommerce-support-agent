# backend/app/services/embedding_service.py
"""Embedding 服务：硅基流动 embeddings API + 本地哈希向量兜底（代替 Milvus 的向量生成层）"""
import hashlib
import math
import re
from typing import List

import numpy as np

from app.core.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# 兜底向量的维度（API 不可用时使用字符 n-gram 哈希向量）
FALLBACK_DIM = 256


class EmbeddingService:
    """Embedding 服务，带内存缓存"""

    def __init__(self):
        self._cache: dict[str, np.ndarray] = {}
        self._client = None
        if settings.LLM_API_KEY:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                timeout=30.0,
                max_retries=1,
            )
        self.api_failed = False  # 连续失败后直接走本地兜底，避免每次请求都超时

    async def embed(self, texts: List[str]) -> np.ndarray:
        """批量向量化，返回 (n, dim) 归一化矩阵"""
        results: list[np.ndarray | None] = []
        missing_idx: list[int] = []
        missing_texts: list[str] = []

        for i, t in enumerate(texts):
            cached = self._cache.get(t)
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)
                missing_idx.append(i)
                missing_texts.append(t)

        if missing_texts:
            vectors = await self._embed_remote(missing_texts)
            for j, vec in zip(missing_idx, vectors):
                self._cache[missing_texts[j]] = vec
                results[j] = vec

        return np.array(results)

    async def embed_one(self, text: str) -> np.ndarray:
        return (await self.embed([text]))[0]

    async def _embed_remote(self, texts: List[str]) -> list[np.ndarray]:
        """调用硅基流动 embeddings API，失败时本地兜底"""
        if self._client and not self.api_failed:
            try:
                out: list[np.ndarray] = []
                for start in range(0, len(texts), settings.EMBEDDING_BATCH_SIZE):
                    batch = texts[start:start + settings.EMBEDDING_BATCH_SIZE]
                    resp = await self._client.embeddings.create(
                        model=settings.EMBEDDING_MODEL,
                        input=batch,
                    )
                    for item in resp.data:
                        vec = np.array(item.embedding, dtype=np.float32)
                        norm = np.linalg.norm(vec)
                        if norm > 0:
                            vec = vec / norm
                        out.append(vec)
                return out
            except Exception as e:
                logger.warning(f'Embedding API 调用失败，降级为本地哈希向量: {e}')
                self.api_failed = True

        return [self._fallback_vector(t) for t in texts]

    @staticmethod
    def _fallback_vector(text: str) -> np.ndarray:
        """本地兜底：字符 2/3-gram 哈希向量（无需网络，语义能力弱但可离线运行）"""
        vec = np.zeros(FALLBACK_DIM, dtype=np.float32)
        text = re.sub(r'\s+', '', text.lower())
        for n in (2, 3):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                h = int(hashlib.md5(gram.encode('utf-8')).hexdigest(), 16)
                vec[h % FALLBACK_DIM] += 1.0
        norm = math.sqrt(float((vec ** 2).sum()))
        if norm > 0:
            vec = vec / norm
        return vec


# 全局单例
embedding_service = EmbeddingService()
