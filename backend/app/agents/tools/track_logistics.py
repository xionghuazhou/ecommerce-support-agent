# backend/app/agents/tools/track_logistics.py
"""真实联网快递轨迹查询工具：用户给一个真实快递单号，实时查快递100官方数据"""
import re
from typing import Dict, Any

from app.agents.tools.base import BaseTool
from app.services.logistics_service import track_express
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TrackLogisticsTool(BaseTool):
    """快递轨迹查询工具（真实联网）

    与 query_order 的区别：query_order 查本商城订单库；本工具直接查快递官方的实时轨迹，
    任何平台的快递单号都能查（顺丰/圆通/中通/京东/极兔等）。
    """
    name = 'track_logistics'
    description = '实时联网查询快递单号的官方物流轨迹（支持顺丰/圆通/中通/京东/EMS/极兔等主流快递）'
    parameters = {
        'type': 'object',
        'properties': {
            'tracking_no': {'type': 'string', 'description': '快递运单号，如 SF1392690203975'}
        },
        'required': ['tracking_no']
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tracking_no = (params.get('tracking_no') or '').strip()
            user_message = params.get('user_message', '')

            # 用户原话优先：小模型转述单号时常丢数字（如 JDX057985520250 -> JDX57985520），
            # 原话里能提取到运单号就一律以原话为准
            extracted = None
            if user_message:
                cleaned = user_message.replace(' ', '')
                m_order = re.search(r'ORDER\d{6,}', cleaned, re.IGNORECASE)
                for cand in re.findall(r'[A-Za-z]{1,4}\d{9,}|\d{12,}', cleaned):
                    if re.fullmatch(r'1[3-9]\d{9}', cand):
                        continue
                    if m_order and cand.upper() in m_order.group().upper():
                        continue
                    extracted = cand.upper()
                    break
            if extracted:
                tracking_no = extracted
            else:
                tracking_no = tracking_no.replace(' ', '').upper()

            if not tracking_no:
                return {'success': False,
                        'response': '请告诉我需要查询的快递单号（例如 SF1392690203975），我马上帮你实时查询物流轨迹。',
                        'data': {}}

            result = await track_express(tracking_no)
            if not result.get('success'):
                return {'success': False, 'response': result.get('message', '查询失败'), 'data': {}}

            text = (
                f"🚚 {result['carrier_name']} {tracking_no}\n"
                f"当前状态：{result['state_text']}\n\n"
                f"最新轨迹：\n{result['trace_text']}"
            )
            return {'success': True, 'response': text,
                    'data': {'carrier': result['carrier_name'], 'state': result['state_text'],
                             'trace_count': len(result['trace'])}}
        except Exception as e:
            logger.error(f'快递轨迹查询失败: {e}')
            return {'success': False, 'response': '物流查询出现异常，请稍后重试', 'data': {}}
