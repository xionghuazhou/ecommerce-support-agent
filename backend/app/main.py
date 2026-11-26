# backend/app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func

from app.api.v1 import chat, intent, knowledge, order, product, analytics
from app.core.config import settings, FRONTEND_STATIC_DIR
from app.core.database import engine, Base, AsyncSessionLocal
from app.models import Intent
from app.services.rag_service import rag_service
from app.services.intent_service import intent_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时建表 + 初始化数据 + 构建向量/语义索引"""
    logger.info('应用启动中...')

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 启用 WAL 模式（持久化到库文件）：推理模型请求耗时 15-40s，
        # 长读事务不再阻塞其他请求的写入，避免 database is locked
        from sqlalchemy import text
        await conn.execute(text('PRAGMA journal_mode=WAL'))

    async with AsyncSessionLocal() as db:
        # 首次启动自动初始化种子数据（幂等）
        count = (await db.execute(select(func.count(Intent.id)))).scalar() or 0
        if count == 0:
            logger.info('检测到空库，自动初始化种子数据与知识库...')
            from scripts.seed_data import seed_all
            from scripts.import_knowledge import import_knowledge
            await seed_all(db)
            await import_knowledge(db)

        # RAG 向量索引
        await rag_service.load_index(db)

        # 意图示例语料语义索引
        intents = (await db.execute(select(Intent).where(Intent.is_active == True))).scalars().all()  # noqa: E712
        samples = []
        for it in intents:
            for utterance in (it.sample_utterances or '').split(';'):
                if utterance.strip():
                    samples.append((utterance.strip(), it.intent_code, it.intent_name,
                                    it.handler_type, it.priority))
        await intent_service.build_semantic_index_async(samples)

    logger.info(f'应用启动完成: {settings.PROJECT_NAME} v{settings.VERSION}')
    yield
    logger.info('应用已关闭')
    await engine.dispose()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description='电商智能客服系统 API（LLM + RAG + NLU + 情感分析 + ReAct Agent）',
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 注册路由
app.include_router(chat.router, prefix='/api/v1/chat', tags=['对话服务'])
app.include_router(intent.router, prefix='/api/v1/intent', tags=['意图识别'])
app.include_router(knowledge.router, prefix='/api/v1/knowledge', tags=['知识库'])
app.include_router(order.router, prefix='/api/v1/order', tags=['订单服务'])
app.include_router(product.router, prefix='/api/v1/product', tags=['商品服务'])
app.include_router(analytics.router, prefix='/api/v1/analytics', tags=['数据分析'])


@app.get('/health', tags=['系统'])
async def health():
    """健康检查（含 LLM / Embedding 服务状态）"""
    from app.services.llm_service import llm_service
    from app.services.embedding_service import embedding_service
    return {
        'status': 'ok',
        'project': settings.PROJECT_NAME,
        'version': settings.VERSION,
        'llm': {'enabled': llm_service.is_available, 'model': settings.LLM_MODEL,
                'base_url': settings.LLM_BASE_URL},
        'embedding': {'model': settings.EMBEDDING_MODEL, 'mode':
                      'api' if not embedding_service.api_failed else 'fallback'},
        'rag_items': len(rag_service._items),
    }


# 前端静态页面（Vue3 CDN 单页应用）
app.mount('/', StaticFiles(directory=str(FRONTEND_STATIC_DIR), html=True), name='static')
