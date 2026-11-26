# backend/app/schemas/chat.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SentimentType(str, Enum):
    POSITIVE = 'positive'
    NEUTRAL = 'neutral'
    NEGATIVE = 'negative'


class SenderType(str, Enum):
    USER = 'user'
    BOT = 'bot'
    AGENT = 'agent'


# ============ 请求模型 ============

class SendMessageRequest(BaseModel):
    session_id: str = Field(..., description='会话ID')
    content: str = Field(..., min_length=1, max_length=2000, description='消息内容')
    user_id: Optional[int] = Field(None, description='用户ID')
    content_type: str = Field('text', description='内容类型')
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description='元数据')


class CreateSessionRequest(BaseModel):
    user_id: Optional[int] = Field(None, description='用户ID')
    channel: str = Field('web', description='渠道来源')


class TransferRequest(BaseModel):
    session_id: str = Field(..., description='会话ID')
    reason: Optional[str] = Field('用户主动请求', description='转接原因')


class RateRequest(BaseModel):
    session_id: str = Field(..., description='会话ID')
    score: int = Field(..., ge=1, le=5, description='满意度评分 1-5')
    comment: Optional[str] = Field(None, description='评价内容')


# ============ 响应模型 ============

class IntentInfo(BaseModel):
    intent_code: str
    intent_name: str
    confidence: float
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    handler_type: str
    priority: int = 0


class MessageResponse(BaseModel):
    id: int
    session_id: str
    sender_type: SenderType
    content: str
    content_type: str
    intent_code: Optional[str] = None
    intent_name: Optional[str] = None
    intent_confidence: Optional[float] = None
    sentiment: Optional[SentimentType] = None
    sentiment_score: Optional[float] = None
    is_human_transfer: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class SendMessageResponse(BaseModel):
    response: str = Field(..., description='回复内容')
    intent: IntentInfo = Field(..., description='意图信息')
    sentiment: SentimentType = Field(..., description='情感类型')
    sentiment_score: float = Field(..., description='情感得分')
    quick_replies: List[str] = Field(default_factory=list, description='快捷回复')
    need_transfer: bool = Field(False, description='是否需要转人工')
    tool_trace: List[Dict[str, Any]] = Field(default_factory=list, description='Agent 工具调用轨迹')
    response_strategy: Dict[str, Any] = Field(default_factory=dict, description='情感响应策略')
    session_id: str = Field(..., description='会话ID')
    message_id: int = Field(0, description='机器人消息ID')


class SessionInfo(BaseModel):
    session_id: str
    user_id: Optional[int]
    status: str
    started_at: datetime
    message_count: int = 0
    bot_name: str = '智能客服小e'


class CreateSessionResponse(BaseModel):
    session: SessionInfo
    welcome_message: str
    quick_replies: List[str] = Field(default_factory=list)
