# backend/app/schemas/intent.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class Entity(BaseModel):
    type: str
    value: str
    start: int = 0
    end: int = 0


class IntentResult(BaseModel):
    """意图识别结果"""
    intent_code: str = 'fallback'
    intent_name: str = '其他'
    confidence: float = 0.5
    entities: List[Entity] = Field(default_factory=list)
    handler_type: str = 'llm'
    priority: int = 0
    source: str = Field('', description='识别来源 keyword/semantic/llm/fuse')

    def to_info(self) -> Dict[str, Any]:
        return {
            'intent_code': self.intent_code,
            'intent_name': self.intent_name,
            'confidence': round(self.confidence, 4),
            'entities': [e.model_dump() for e in self.entities],
            'handler_type': self.handler_type,
            'priority': self.priority,
        }


class RecognizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description='待识别文本')


class IntentItem(BaseModel):
    id: int
    intent_code: str
    intent_name: str
    description: Optional[str] = None
    handler_type: str
    priority: int

    class Config:
        from_attributes = True
