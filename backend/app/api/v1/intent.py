# backend/app/api/v1/intent.py
"""意图识别接口"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Intent
from app.schemas.intent import RecognizeRequest, IntentResult, IntentItem
from app.services.intent_service import intent_service
from app.services.sentiment_service import sentiment_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.post('/recognize')
async def recognize(req: RecognizeRequest, db: AsyncSession = Depends(get_db)):
    """识别文本的意图 + 情感（NLU 演示接口）"""
    intent: IntentResult = await intent_service.recognize(req.text)
    sentiment, score = await sentiment_service.analyze(req.text)
    return {
        'text': req.text,
        'intent': intent.to_info(),
        'sentiment': sentiment.value,
        'sentiment_score': score,
    }


@router.get('/list', response_model=List[IntentItem])
async def list_intents(db: AsyncSession = Depends(get_db)):
    """意图列表"""
    result = await db.execute(select(Intent).where(Intent.is_active == True).order_by(Intent.id))  # noqa: E712
    return result.scalars().all()
