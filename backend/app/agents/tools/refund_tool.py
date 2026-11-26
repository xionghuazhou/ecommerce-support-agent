# backend/app/agents/tools/refund_tool.py
from typing import Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool
from app.agents.tools.query_order import STATUS_NAMES, format_order
from app.models.order import Order
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class RefundTool(BaseTool):
    """退款退货工具

    处理退款申请、退货流程、取消订单
    """
    name = 'refund'
    description = '处理退款退货申请、取消订单、查询退款进度'
    parameters = {
        'type': 'object',
        'properties': {
            'action': {'type': 'string', 'enum': ['cancel', 'return', 'refund', 'query'], 'description': '操作类型'},
            'order_no': {'type': 'string', 'description': '订单号'},
            'reason': {'type': 'string', 'description': '原因'}
        },
        'required': ['action']
    }
    requires_auth = True

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            db: AsyncSession | None = params.get('db')
            if db is None:
                return {'success': False, 'response': '数据库会话不可用', 'data': {}}

            user_message = params.get('user_message', '')
            user_id = params.get('user_id')

            logger.info(f'退款处理: {user_message[:50]}')

            action = params.get('action')
            # 未指定动作时按关键词判断（关键词兜底逻辑）
            if not action:
                if any(word in user_message for word in ['取消', '撤单', '不要了']):
                    action = 'cancel'
                elif any(word in user_message for word in ['退货', '退回']):
                    action = 'return'
                elif any(word in user_message for word in ['退款', '退钱', '返款']):
                    action = 'refund'
                else:
                    action = 'query'

            if action == 'query':
                return await self._handle_refund_query(db, user_id)

            order = await self._find_order(db, params.get('order_no'), user_message, user_id)
            if isinstance(order, dict):  # 返回了错误信息
                return {**order, 'data': {}}

            if action == 'cancel':
                return await self._handle_cancel_order(db, order)
            elif action == 'return':
                return await self._handle_return_goods(db, order)
            else:
                return await self._handle_refund(db, order)
        except Exception as e:
            logger.error(f'退款处理失败: {e}')
            return {'success': False, 'response': '退款处理出现异常，请稍后重试', 'data': {}}

    async def _find_order(self, db: AsyncSession, order_no: Optional[str],
                          user_message: str, user_id) -> Order | Dict[str, Any]:
        """定位订单；找不到时返回错误 dict"""
        from app.agents.tools.query_order import sanitize_order_no
        order_no = sanitize_order_no(order_no, user_message)

        if not order_no:
            # 取该用户最近一笔可操作的订单
            if user_id:
                result = await db.execute(
                    select(Order).where(Order.user_id == user_id)
                    .where(Order.status.in_(['paid', 'shipped', 'delivered']))
                    .order_by(Order.created_at.desc()).limit(1)
                )
                order = result.scalar_one_or_none()
                if order:
                    return order
            return {'success': False,
                    'response': '请告诉我需要处理的订单号（例如 ORDER20260815001），我来为您办理。'}

        result = await db.execute(select(Order).where(Order.order_no == order_no.upper()))
        order = result.scalar_one_or_none()
        if not order:
            return {'success': False, 'response': f'未找到订单 {order_no}，请核对订单号。'}
        if user_id and order.user_id != user_id:
            return {'success': False, 'response': '该订单不属于当前用户，无法操作。'}
        return order

    async def _handle_cancel_order(self, db: AsyncSession, order: Order) -> Dict[str, Any]:
        if order.status in ('shipped', 'delivered', 'completed'):
            text = (f'订单 {order.order_no} 已{STATUS_NAMES.get(order.status, order.status)}，'
                    f'无法直接取消。如不需要，可以为您办理退货退款，需要吗？')
            return {'success': False, 'response': text, 'data': {'order_status': order.status}}
        if order.status in ('cancelled', 'refunding', 'refunded'):
            return {'success': True, 'response': f'订单 {order.order_no} 当前为「{STATUS_NAMES.get(order.status, order.status)}」状态，无需重复操作。',
                    'data': {}}

        order.status = 'cancelled'
        order.remark = '用户通过智能客服取消订单'
        await db.commit()
        response = (
            f'✅ 订单取消成功\n\n{format_order(order)}\n\n'
            f'如该订单已支付，退款将在 1-3 个工作日内原路退回。'
        )
        logger.info(f'订单已取消: {order.order_no}')
        return {'success': True, 'response': response, 'data': {'order_no': order.order_no, 'status': 'cancelled'}}

    async def _handle_return_goods(self, db: AsyncSession, order: Order) -> Dict[str, Any]:
        if order.status not in ('shipped', 'delivered', 'completed'):
            return {'success': False,
                    'response': f'订单 {order.order_no} 尚未签收（当前：{STATUS_NAMES.get(order.status, order.status)}），'
                                f'可以直接取消订单，无需办理退货。',
                    'data': {}}
        order.status = 'refunding'
        order.remark = '用户申请退货退款'
        await db.commit()
        response = (
            f'✅ 退货申请已提交\n\n{format_order(order)}\n\n'
            f'📦 退货流程：\n'
            f'1. 审核通过后系统会发送退货地址短信给您\n'
            f'2. 请在 7 天内寄回商品并填写运单号\n'
            f'3. 仓库验收后 1-3 个工作日内退款原路退回\n\n'
            f'退货运费已为您承担，全程免费。'
        )
        return {'success': True, 'response': response, 'data': {'order_no': order.order_no, 'status': 'refunding'}}

    async def _handle_refund(self, db: AsyncSession, order: Order) -> Dict[str, Any]:
        if order.status == 'refunded':
            return {'success': True, 'response': f'订单 {order.order_no} 已完成退款，请注意查收。', 'data': {}}
        if order.status == 'pending_payment':
            return {'success': False, 'response': f'订单 {order.order_no} 尚未支付，无需退款，可直接取消订单。', 'data': {}}

        order.status = 'refunding'
        order.remark = '用户申请仅退款'
        await db.commit()
        response = (
            f'✅ 退款申请已提交\n\n{format_order(order)}\n\n'
            f'💰 退款说明：\n'
            f'- 审核时长：24 小时内\n'
            f'- 退款路径：原支付渠道原路退回\n'
            f'- 到账时间：审核通过后 1-3 个工作日\n\n'
            f'您可以在「订单详情-退款进度」随时查看进度。'
        )
        return {'success': True, 'response': response, 'data': {'order_no': order.order_no, 'status': 'refunding'}}

    async def _handle_refund_query(self, db: AsyncSession, user_id) -> Dict[str, Any]:
        if not user_id:
            return {'success': False, 'response': '请提供订单号查询退款进度。', 'data': {}}
        result = await db.execute(
            select(Order).where(Order.user_id == user_id)
            .where(Order.status.in_(['refunding', 'refunded', 'cancelled']))
            .order_by(Order.created_at.desc()).limit(5)
        )
        orders = result.scalars().all()
        if not orders:
            return {'success': True, 'response': '您名下暂无退款/取消记录的订单。', 'data': {}}
        text = '您的退款/售后订单：\n\n' + '\n\n'.join(format_order(o, detail=False) for o in orders)
        return {'success': True, 'response': text, 'data': {}}
