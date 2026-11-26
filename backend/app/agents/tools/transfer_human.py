# backend/app/agents/tools/transfer_human.py
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool
from app.models.session import Session
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TransferHumanTool(BaseTool):
    """转人工客服工具

    将用户请求转接给人工客服
    """
    name = 'transfer_human'
    description = '将用户转接给人工客服，处理复杂问题'
    parameters = {
        'type': 'object',
        'properties': {
            'reason': {'type': 'string', 'enum': ['用户主动请求', '投诉', '技术问题', '其他'],
                       'description': '转接原因'}
        },
        'required': ['reason']
    }

    def __init__(self):
        self.queue_name = 'human_agent_queue'

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行转人工"""
        try:
            session_id = params.get('session_id', '')
            user_id = params.get('user_id')
            reason = params.get('reason', '用户主动请求')

            logger.info(f'转人工: session={session_id}, user={user_id}, reason={reason}')

            # 1. 更新会话状态
            transfer_result = await self._queue_transfer(params.get('db'), session_id, user_id, reason)

            # 2. 生成转接消息
            message = self._generate_transfer_message(reason, transfer_result)

            return {
                'success': True,
                'response': message,
                'transfer_id': transfer_result.get('transfer_id'),
                'queue_position': transfer_result.get('position'),
                'estimated_wait_time': transfer_result.get('wait_time'),
                'need_transfer': True,
            }
        except Exception as e:
            logger.error(f'转人工失败: {e}')
            return {'success': False, 'response': '转接人工失败，请稍后重试或拨打客服热线 400-800-1234', 'data': {}}

    async def _queue_transfer(self, db: AsyncSession | None, session_id: str,
                              user_id, reason: str) -> Dict[str, Any]:
        """更新会话状态为 transferred，模拟排队"""
        if db is not None and session_id:
            result = await db.execute(select(Session).where(Session.session_id == session_id))
            session = result.scalar_one_or_none()
            if session:
                session.status = 'transferred'
                await db.commit()

        import random
        position = random.randint(1, 3)
        return {
            'transfer_id': f'TF{int(__import__("time").time())}',
            'position': position,
            'wait_time': position * 60,
        }

    @staticmethod
    def _generate_transfer_message(reason: str, transfer_result: Dict[str, Any]) -> str:
        position = transfer_result.get('position', 1)
        wait = transfer_result.get('wait_time', 60)
        minutes = max(1, round(wait / 60))
        return (
            f'👋 好的，正在为您转接人工客服（原因：{reason}）\n\n'
            f'当前排队第 {position} 位，预计等待约 {minutes} 分钟。\n'
            f'请稍候，不要关闭窗口，人工客服将尽快为您服务。'
        )
