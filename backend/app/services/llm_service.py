# backend/app/services/llm_service.py
"""LLM 服务：OpenAI 兼容接口（默认硅基流动）。
未配置 key 或调用失败时返回 None，由上层走模板兜底，保证系统可用。"""
from typing import List, Dict, Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class LLMService:
    """LLM 服务"""

    def __init__(self):
        if settings.LLM_API_KEY:
            self.client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                timeout=120.0,  # DeepSeek-V4-Flash 为推理模型，带思考过程，超时放宽
                max_retries=1,
            )
            self.enabled = True
            logger.info(f'LLM 服务已启用: {settings.LLM_BASE_URL} / {settings.LLM_MODEL}')
        else:
            self.client = None
            self.enabled = False
            logger.warning('未配置 LLM_API_KEY，将使用关键词模板回复兜底')

    @property
    def is_available(self) -> bool:
        return self.enabled

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None,
                   max_tokens: Optional[int] = None) -> Optional[str]:
        """对话补全，失败返回 None"""
        if not self.enabled:
            return None
        try:
            resp = await self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            )
            content = resp.choices[0].message.content
            if content:
                return content.strip()
            return None
        except Exception as e:
            logger.error(f'LLM 调用失败: {e}')
            return None

    async def generate(self, prompt: str, system_prompt: Optional[str] = None,
                       temperature: float = 0.7, json_mode: bool = False) -> Optional[str]:
        """单轮生成"""
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})
        if json_mode:
            messages[0 if system_prompt else -1]['content'] += '\n只输出 JSON，不要输出其他内容。'
        return await self.chat(messages, temperature=temperature)


# 全局单例
llm_service = LLMService()
