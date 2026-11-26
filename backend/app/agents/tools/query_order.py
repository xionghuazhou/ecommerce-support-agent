# backend/app/agents/tools/query_order.py
from typing import Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import BaseTool
from app.models.order import Order
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

STATUS_NAMES = {
    'pending_payment': '待支付',
    'paid': '已支付，待发货',
    'shipped': '已发货',
    'delivered': '已送达',
    'completed': '已完成',
    'cancelled': '已取消',
    'refunding': '退款中',
    'refunded': '已退款',
}


def format_order(order: Order, detail: bool = True) -> str:
    """格式化订单信息（供工具回复与 LLM Observation 复用）"""
    status = STATUS_NAMES.get(order.status, order.status)
    lines = [
        f"📦 订单号：{order.order_no}",
        f"商品：{order.product_name} × {order.quantity}",
        f"金额：￥{order.total_amount}",
        f"状态：{status}",
    ]
    if detail:
        if order.shipping_company:
            lines.append(f"物流：{order.shipping_company} {order.tracking_no or '待分配单号'}")
        if order.receiver_address:
            lines.append(f"收货：{order.receiver_name or ''} {order.receiver_address}")
    lines.append(f"下单时间：{order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else '-'}")
    return '\n'.join(lines)


def sanitize_order_no(value: str | None, user_message: str = '') -> str | None:
    """校验/提取订单号。

    小模型在 ReAct 中经常抄错长数字（如 ORDER20260815001 -> ORDER2226815），
    因此用户原话里能提取到订单号时一律以原话为准，LLM 传参仅作兜底。
    """
    import re

    def _valid(v: str) -> str | None:
        v = v.replace(' ', '').upper()
        return v if re.fullmatch(r'ORDER\d{6,}', v) else None

    if user_message:
        match = re.search(r'ORDER\s?\d{6,}', user_message, re.IGNORECASE)
        if match:
            cleaned = _valid(match.group())
            if cleaned:
                return cleaned
    if value:
        return _valid(str(value))
    return None


class QueryOrderTool(BaseTool):
    """订单查询工具"""
    name = 'query_order'
    description = '查询用户订单状态、物流信息、收货地址等'
    parameters = {
        'type': 'object',
        'properties': {
            'order_no': {'type': 'string', 'description': '订单号（可选）'}
        },
        'required': []
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            db: AsyncSession | None = params.get('db')
            if db is None:
                return {'success': False, 'response': '数据库会话不可用', 'data': {}}

            user_id = params.get('user_id')
            order_no = sanitize_order_no(params.get('order_no'), params.get('user_message', ''))

            if order_no:
                result = await db.execute(select(Order).where(Order.order_no == order_no.upper()))
                order = result.scalar_one_or_none()
                if not order:
                    return {
                        'success': False,
                        'response': f'未找到订单号为 {order_no} 的订单，请核对后重试。',
                        'data': {}
                    }
                # 越权保护：带 user_id 时校验归属
                if user_id and order.user_id != user_id:
                    return {'success': False, 'response': '该订单不属于当前用户，无法查询。', 'data': {}}
                text = format_order(order)
                # 已发货/已送达订单：实时联网查询快递官方轨迹（快递100）
                if order.status in ('shipped', 'delivered') and order.tracking_no:
                    from app.services.logistics_service import track_express
                    real = await track_express(order.tracking_no)
                    if real.get('success'):
                        text += (f"\n\n🚚 实时物流轨迹（{real['carrier_name']}·联网查询，当前：{real['state_text']}）：\n"
                                 + real['trace_text'])
                    else:
                        text += (f"\n\n（运单 {order.tracking_no} 暂未在快递官方查到轨迹——本演示订单使用的是虚构单号。"
                                 f"你直接发我一个真实的快递单号，我可以实时联网查询。）")
                return {'success': True, 'response': text,
                        'data': {'order': {'order_no': order.order_no, 'status': order.status,
                                           'product_name': order.product_name,
                                           'total_amount': float(order.total_amount),
                                           'tracking_no': order.tracking_no}}}

            # 无订单号：返回该用户最近订单列表
            if not user_id:
                return {'success': False, 'response': '请提供订单号，或先登录后查询名下订单。', 'data': {}}
            result = await db.execute(
                select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(5)
            )
            orders: List[Order] = result.scalars().all()
            if not orders:
                return {'success': True, 'response': '您名下暂无订单记录。', 'data': {'orders': []}}
            text = f'您最近 {len(orders)} 笔订单：\n\n' + '\n\n'.join(format_order(o, detail=False) for o in orders)
            return {'success': True, 'response': text,
                    'data': {'orders': [{'order_no': o.order_no, 'status': o.status} for o in orders]}}
        except Exception as e:
            logger.error(f'订单查询失败: {e}')
            return {'success': False, 'response': '订单查询出现异常，请稍后重试', 'data': {}}
