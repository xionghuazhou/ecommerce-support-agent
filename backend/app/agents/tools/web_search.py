# backend/app/agents/tools/web_search.py
"""真实联网搜索工具：用必应搜索最新信息（新闻/天气/行情/外部常识等）"""
from typing import Dict, Any

from app.agents.tools.base import BaseTool
from app.services.web_search_service import web_search
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class WebSearchTool(BaseTool):
    """联网搜索工具（真实联网）

    用于知识库没有、且需要最新/外部信息的场景：新闻、天气、行情、赛事、
    外部常识等。商城内部业务（订单/政策/商品）优先用其他专用工具。
    """
    name = 'web_search'
    description = '实时联网搜索最新信息（新闻、天气、赛事、行情、外部常识等），返回网页标题、摘要与来源'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': '搜索关键词'}
        },
        'required': ['query']
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = (params.get('query') or '').strip()
            # 未给参数时用用户原话兜底（去掉口语化前缀）
            if not query and params.get('user_message'):
                query = params['user_message']

            if not query:
                return {'success': False, 'response': '请告诉我需要搜索的内容', 'data': {}}

            result = await web_search(query)
            if not result.get('success'):
                return {'success': False, 'response': result.get('message', '搜索失败'), 'data': {}}

            lines = [f'🔍 「{query}」的联网搜索结果：\n']
            for i, r in enumerate(result['results'], 1):
                lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   来源: {r['url']}")
            text = '\n\n'.join(lines)

            return {'success': True, 'response': text,
                    'data': {'count': len(result['results']),
                             'results': result['results']}}
        except Exception as e:
            logger.error(f'联网搜索工具执行失败: {e}')
            return {'success': False, 'response': '联网搜索出现异常，请稍后重试', 'data': {}}
