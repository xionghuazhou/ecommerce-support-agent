# backend/app/agents/tools/search_knowledge.py
from typing import Dict, Any, List, Optional

from app.agents.tools.base import BaseTool
from app.services.rag_service import rag_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class SearchKnowledgeTool(BaseTool):
    """知识库检索工具

    从知识库中检索与用户问题最相关的内容（RAG）
    """
    name = 'search_knowledge'
    description = '从知识库中检索商品信息、平台政策、常见问题等'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': '搜索关键词'},
            'category': {'type': 'string', 'description': '知识库分类（可选）'}
        },
        'required': ['query']
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = params.get('query', '')
            if not query:
                return {'success': False, 'response': '缺少搜索关键词', 'data': {}}

            hits: List[Dict[str, Any]] = await rag_service.search(query)

            if not hits:
                return {
                    'success': True,
                    'response': '知识库中未找到与该问题相关的内容，建议转人工客服进一步咨询。',
                    'data': {'hits': []}
                }

            lines = []
            for i, hit in enumerate(hits, 1):
                lines.append(f"[{i}]（{hit['category']}，相关度{hit['score']:.0%}）\n"
                             f"问：{hit['question']}\n答：{hit['answer']}")
            response = '\n\n'.join(lines)

            # 异步更新命中次数（不阻塞主流程）
            db = params.get('db')
            if db is not None:
                try:
                    await rag_service.increment_hit_count(db, [h['id'] for h in hits])
                except Exception as e:
                    logger.warning(f'更新命中次数失败: {e}')

            return {
                'success': True,
                'response': response,
                'data': {'hits': hits}
            }
        except Exception as e:
            logger.error(f'知识库检索失败: {e}')
            return {'success': False, 'response': '知识库检索出现异常，请稍后重试', 'data': {}}
