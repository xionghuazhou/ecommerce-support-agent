# backend/scripts/init_db.py
"""初始化数据库：建表 + 种子数据 + 知识库导入 + 意图语义索引

用法（在 backend 目录下）：
    python scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import engine, AsyncSessionLocal, Base  # noqa: E402
from app.models import __all__ as _models  # noqa: F401,E402  确保模型已注册
import app.models  # noqa: E402
from scripts.seed_data import seed_all  # noqa: E402
from scripts.import_knowledge import import_knowledge  # noqa: E402
from app.services.rag_service import rag_service  # noqa: E402
from app.services.embedding_service import embedding_service  # noqa: E402
from app.services.intent_service import intent_service  # noqa: E402
from app.models import Intent  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


async def build_intent_semantic_index():
    """用意图示例语料构建语义匹配索引"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Intent).where(Intent.is_active == True))  # noqa: E712
        intents = result.scalars().all()
        samples = []
        for it in intents:
            for utterance in (it.sample_utterances or '').split(';'):
                if utterance.strip():
                    samples.append((utterance.strip(), it.intent_code, it.intent_name,
                                    it.handler_type, it.priority))
        await intent_service.build_semantic_index_async(samples)
        print(f'✅ 意图语义索引构建完成（{len(samples)} 条示例语料）')


async def main():
    print('=== 数据库初始化开始 ===')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('✅ 数据表创建完成')

    async with AsyncSessionLocal() as db:
        await seed_all(db)
        print('✅ 种子数据写入完成')
        count = await import_knowledge(db)
        print(f'✅ 知识库导入完成（{count} 条）')
        await rag_service.load_index(db, force=True)
        mode = '远程API' if not embedding_service.api_failed else '本地降级'
        print(f'✅ RAG 向量索引就绪（Embedding 模式：{mode}）')

    await build_intent_semantic_index()
    await engine.dispose()
    print('=== 数据库初始化完成 ===')


if __name__ == '__main__':
    asyncio.run(main())
