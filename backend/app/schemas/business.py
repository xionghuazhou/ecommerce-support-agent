# backend/app/schemas/business.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============ 订单 ============

class OrderInfo(BaseModel):
    id: int
    order_no: str
    status: str
    product_name: str
    quantity: int
    total_amount: float
    tracking_no: Optional[str] = None
    shipping_company: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 商品 ============

class ProductInfo(BaseModel):
    id: int
    name: str
    category: str
    price: float
    description: Optional[str] = None
    stock: int
    sales: int
    promotion: Optional[str] = None

    class Config:
        from_attributes = True


# ============ 知识库 ============

class KnowledgeCreateRequest(BaseModel):
    category: str = Field(..., description='知识分类')
    question: str = Field(..., description='问题')
    answer: str = Field(..., description='答案')
    keywords: Optional[str] = Field(None, description='关键词，逗号分隔')


class KnowledgeInfo(BaseModel):
    id: int
    category: str
    question: str
    answer: str
    keywords: Optional[str] = None
    hit_count: int = 0
    is_active: bool = True

    class Config:
        from_attributes = True


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., description='搜索问题')
    top_k: int = Field(5, ge=1, le=10, description='返回条数')


# ============ 数据分析 ============

class AnalyticsOverview(BaseModel):
    total_sessions: int = 0
    today_sessions: int = 0
    total_messages: int = 0
    ai_resolve_rate: float = 0.0
    transfer_rate: float = 0.0
    avg_response_seconds: float = 0.0
    avg_satisfaction: float = 0.0
    intent_distribution: List[Dict[str, Any]] = Field(default_factory=list)
    sentiment_distribution: Dict[str, int] = Field(default_factory=dict)
