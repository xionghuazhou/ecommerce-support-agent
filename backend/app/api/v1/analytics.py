# backend/app/api/v1/analytics.py
"""数据分析接口：数据看板核心指标（核心指标体系）"""
from datetime import datetime, timedelta
from typing import Dict, Any, List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Session, Message
from app.schemas.business import AnalyticsOverview
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get('/overview', response_model=AnalyticsOverview)
async def overview(db: AsyncSession = Depends(get_db)):
    """数据看板总览"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    total_sessions = (await db.execute(select(func.count(Session.id)))).scalar() or 0
    today_sessions = (await db.execute(
        select(func.count(Session.id)).where(Session.started_at >= today_start)
    )).scalar() or 0
    transferred = (await db.execute(
        select(func.count(Session.id)).where(Session.status == 'transferred')
    )).scalar() or 0
    rated = (await db.execute(
        select(func.avg(Session.satisfaction_score)).where(Session.satisfaction_score.isnot(None))
    )).scalar()

    total_messages = (await db.execute(select(func.count(Message.id)))).scalar() or 0

    # 意图分布（用户消息）
    intent_rows = (await db.execute(
        select(Message.intent_name, func.count(Message.id))
        .where(Message.sender_type == 'user', Message.intent_name.isnot(None))
        .group_by(Message.intent_name)
    )).all()
    total_intents = sum(c for _, c in intent_rows) or 1
    intent_distribution: List[Dict[str, Any]] = [
        {'name': name, 'count': count, 'percent': round(count * 100.0 / total_intents, 1)}
        for name, count in sorted(intent_rows, key=lambda x: -x[1])
    ]

    # 情感分布（用户消息）
    sentiment_rows = (await db.execute(
        select(Message.sentiment, func.count(Message.id))
        .where(Message.sender_type == 'user', Message.sentiment.isnot(None))
        .group_by(Message.sentiment)
    )).all()
    sentiment_distribution: Dict[str, int] = {name or 'unknown': count for name, count in sentiment_rows}

    # 平均响应时长：取最近 500 条机器人消息的 meta_data.elapsed_seconds 均值
    bot_msgs = (await db.execute(
        select(Message.meta_data).where(Message.sender_type == 'bot')
        .order_by(Message.id.desc()).limit(500)
    )).all()
    elapsed_list = [m[0].get('elapsed_seconds') for m in bot_msgs
                    if m[0] and isinstance(m[0].get('elapsed_seconds'), (int, float))]
    avg_elapsed = round(sum(elapsed_list) / len(elapsed_list), 2) if elapsed_list else 0.0

    transfer_rate = round(transferred * 100.0 / total_sessions, 1) if total_sessions else 0.0
    ai_resolve_rate = round(100.0 - transfer_rate, 1) if total_sessions else 0.0

    return AnalyticsOverview(
        total_sessions=total_sessions,
        today_sessions=today_sessions,
        total_messages=total_messages,
        ai_resolve_rate=ai_resolve_rate,
        transfer_rate=transfer_rate,
        avg_response_seconds=avg_elapsed,
        avg_satisfaction=round(float(rated), 2) if rated else 0.0,
        intent_distribution=intent_distribution,
        sentiment_distribution=sentiment_distribution,
    )
