# backend/app/agents/tools/create_ticket.py
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool
from app.models.ticket import Ticket
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

TYPE_NAMES = {'complaint': '投诉', 'refund': '退款', 'consult': '咨询', 'suggestion': '建议'}


class CreateTicketTool(BaseTool):
    """创建工单工具"""
    name = 'create_ticket'
    description = '创建客服工单，记录用户问题和反馈'
    parameters = {
        'type': 'object',
        'properties': {
            'type': {'type': 'string', 'enum': ['complaint', 'refund', 'consult', 'suggestion'],
                     'description': '工单类型'},
            'title': {'type': 'string', 'description': '工单标题'},
            'content': {'type': 'string', 'description': '工单内容'}
        },
        'required': ['type', 'content']
    }
    requires_auth = True

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """创建工单"""
        try:
            db: AsyncSession | None = params.get('db')
            session_id = params.get('session_id', '')
            user_id = params.get('user_id')
            ticket_type = params.get('type', 'consult')
            title = params.get('title') or f'用户{TYPE_NAMES.get(ticket_type, "咨询")}'
            content = params.get('content') or params.get('user_message', '')

            import random
            import time
            ticket_no = f'TKT{int(time.time())}{random.randint(100, 999)}'

            if db is not None:
                db.add(Ticket(ticket_no=ticket_no, session_id=session_id, user_id=user_id,
                              type=ticket_type, title=title, content=content))
                await db.commit()

            return {
                'success': True,
                'response': (
                    f'✅ 工单已创建\n\n'
                    f'工单编号：{ticket_no}\n'
                    f'问题类型：{TYPE_NAMES.get(ticket_type, ticket_type)}\n'
                    f'我们的工作人员将在 24 小时内处理\n\n'
                    f'处理结果会通过短信/站内消息通知您'
                ),
                'ticket_no': ticket_no
            }
        except Exception as e:
            logger.error(f'创建工单失败: {e}')
            return {'success': False, 'response': '工单创建失败，请稍后重试', 'data': {}}
