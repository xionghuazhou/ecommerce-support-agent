# backend/scripts/import_knowledge.py
"""导入知识库（knowledge_base/faqs.json -> knowledge 表 -> 向量化）

用法（在 backend 目录下）：
    python scripts/import_knowledge.py [--file ../knowledge_base/faqs.json]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.config import KNOWLEDGE_BASE_FILE  # noqa: E402
from app.models import Knowledge  # noqa: E402
from app.services.rag_service import rag_service  # noqa: E402
from app.utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


async def import_knowledge(db: AsyncSession, file_path: Path = None, reset: bool = False) -> int:
    """导入知识库（幂等：按 question 去重）"""
    file_path = Path(file_path) if file_path else KNOWLEDGE_BASE_FILE
    with open(file_path, encoding='utf-8') as f:
        faqs = json.load(f)

    if reset:
        await db.execute(delete(Knowledge))
        await db.commit()

    existing = (await db.execute(select(Knowledge.question))).scalars().all()
    existing_set = set(existing)

    count = 0
    for faq in faqs:
        if faq['question'] in existing_set:
            continue
        db.add(Knowledge(category=faq['category'], question=faq['question'],
                         answer=faq['answer'], keywords=faq.get('keywords', ''),
                         embedding_model='BAAI/bge-m3'))
        count += 1
    await db.commit()
    return count


async def main():
    parser = argparse.ArgumentParser(description='导入知识库')
    parser.add_argument('--file', default=str(KNOWLEDGE_BASE_FILE), help='知识库 JSON 文件路径')
    parser.add_argument('--reset', action='store_true', help='清空后重新导入')
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        count = await import_knowledge(db, args.file, reset=args.reset)
        print(f'✅ 导入 {count} 条知识')
        await rag_service.load_index(db, force=True)
        print('✅ 向量索引已重建')
    print('=== 知识库导入完成 ===')


if __name__ == '__main__':
    asyncio.run(main())
