# backend/app/api/v1/chat.py
"""对话服务接口：创建会话 / 发送消息 / 历史消息 / 转人工 / 评价"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Session, Message
from app.schemas.chat import (SendMessageRequest, SendMessageResponse, CreateSessionRequest,
                              CreateSessionResponse, SessionInfo, TransferRequest, RateRequest,
                              MessageResponse, SentimentType, IntentInfo)
from app.agents.customer_agent import CustomerServiceAgent
from app.core.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

# 会话级对话历史缓存（简化版：进程内存代替 Redis）
_session_histories: dict[str, list] = {}

WELCOME_MESSAGE = ('您好！我是智能客服{agent}，很高兴为您服务～\n'
                   '我可以帮您查询订单、了解商品信息、解答售后问题等，请描述您的问题～').format(agent=settings.AGENT_NAME)

DEFAULT_QUICK_REPLIES = ['查一下我的订单', '退换货政策是什么', '有什么优惠活动', '推荐热销商品']


@router.post('/session', response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest = None, db: AsyncSession = Depends(get_db)):
    """创建会话"""
    from app.models import User

    # 未指定用户时使用/创建演示用户
    user_id = req.user_id if req and req.user_id else None
    if user_id is None:
        result = await db.execute(select(User).where(User.username == 'demo_user'))
        user = result.scalar_one_or_none()
        if not user:
            user = User(username='demo_user', phone='13800138000', password_hash='demo')
            db.add(user)
            await db.flush()
        user_id = user.id

    session_id = f'SESS{uuid.uuid4().hex[:24].upper()}'
    session = Session(session_id=session_id, user_id=user_id,
                      channel=req.channel if req else 'web', status='active')
    db.add(session)
    await db.commit()
    await db.refresh(session)

    _session_histories[session_id] = []
    logger.info(f'创建会话: {session_id} (user={user_id})')

    return CreateSessionResponse(
        session=SessionInfo(
            session_id=session.session_id,
            user_id=session.user_id,
            status=session.status,
            started_at=session.started_at,
            message_count=0,
        ),
        welcome_message=WELCOME_MESSAGE,
        quick_replies=DEFAULT_QUICK_REPLIES,
    )


@router.post('/send', response_model=SendMessageResponse)
async def send_message(req: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    """发送消息：走 Agent 完整处理链路（情感分析 -> 意图识别 -> ReAct 工具调用 -> 回复）"""
    result = await db.execute(select(Session).where(Session.session_id == req.session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail='会话不存在，请先创建会话')

    # 保存用户消息
    user_msg = Message(session_row_id=session.id, session_id=session.session_id,
                       sender_type='user', sender_id=session.user_id,
                       content=req.content, content_type=req.content_type)
    db.add(user_msg)
    await db.flush()

    # 构建 Agent（带上会话历史）
    agent = CustomerServiceAgent(db, session.session_id, session.user_id)
    agent.conversation_history = list(_session_histories.get(session.session_id, []))

    started = datetime.now()
    agent_result = await agent.process_message(req.content)
    elapsed = (datetime.now() - started).total_seconds()

    intent = agent_result['intent']
    need_transfer = agent_result['need_transfer']

    # 意图/情感归属用户消息（NLU 分析对象是用户输入，供数据分析）
    user_msg.intent_code = intent.intent_code
    user_msg.intent_name = intent.intent_name
    user_msg.intent_confidence = intent.confidence
    user_msg.sentiment = agent_result['sentiment'].value if hasattr(agent_result['sentiment'], 'value') else str(agent_result['sentiment'])
    user_msg.sentiment_score = agent_result['sentiment_score']

    # 保存机器人回复
    bot_msg = Message(
        session_row_id=session.id, session_id=session.session_id,
        sender_type='bot', content=agent_result['response'],
        is_human_transfer=need_transfer, is_generated=True,
        meta_data={'tool_trace': agent_result['tool_trace'],
                   'response_strategy': agent_result['response_strategy'],
                   'elapsed_seconds': round(elapsed, 2)},
    )
    db.add(bot_msg)
    session.message_count += 2
    session.last_message_at = datetime.now()
    await db.commit()
    await db.refresh(bot_msg)

    # 更新会话历史缓存
    history = _session_histories.setdefault(session.session_id, [])
    history.append({'role': 'user', 'content': req.content})
    history.append({'role': 'assistant', 'content': agent_result['response']})
    if len(history) > 20:
        del history[:-20]

    logger.info(f'会话 {session.session_id} 处理完成: intent={intent.intent_code}, '
                f'sentiment={agent_result["sentiment"]}, {elapsed:.2f}s')

    return SendMessageResponse(
        response=agent_result['response'],
        intent=IntentInfo(**intent.to_info()),
        sentiment=agent_result['sentiment'],
        sentiment_score=agent_result['sentiment_score'],
        quick_replies=agent_result['quick_replies'],
        need_transfer=need_transfer,
        tool_trace=agent_result['tool_trace'],
        response_strategy=agent_result['response_strategy'],
        session_id=session.session_id,
        message_id=bot_msg.id,
    )


@router.get('/history', response_model=List[MessageResponse])
async def get_history(session_id: str = Query(..., description='会话ID'),
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                      db: AsyncSession = Depends(get_db)):
    """获取历史消息（按时间正序）"""
    result = await db.execute(select(Session).where(Session.session_id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail='会话不存在')

    from sqlalchemy import desc
    result = await db.execute(
        select(Message).where(Message.session_row_id == session.id)
        .order_by(desc(Message.id)).offset((page - 1) * page_size).limit(page_size)
    )
    messages = result.scalars().all()
    return list(reversed(messages))


@router.post('/transfer')
async def transfer_to_human(req: TransferRequest, db: AsyncSession = Depends(get_db)):
    """手动转人工"""
    result = await db.execute(select(Session).where(Session.session_id == req.session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail='会话不存在')

    from app.agents.tools import TransferHumanTool
    tool_result = await TransferHumanTool().execute({
        'db': db, 'session_id': req.session_id,
        'user_id': session.user_id, 'reason': req.reason or '用户主动请求',
    })
    return {'success': True, 'message': tool_result['response'],
            'queue_position': tool_result.get('queue_position'),
            'estimated_wait_time': tool_result.get('estimated_wait_time')}


@router.post('/rate')
async def rate_session(req: RateRequest, db: AsyncSession = Depends(get_db)):
    """评价会话"""
    result = await db.execute(select(Session).where(Session.session_id == req.session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail='会话不存在')

    session.satisfaction_score = req.score
    session.satisfaction_comment = req.comment
    if session.status != 'transferred':
        session.status = 'closed'
        session.ended_at = datetime.now()
    await db.commit()
    return {'success': True, 'message': '感谢您的评价！', 'score': req.score}
