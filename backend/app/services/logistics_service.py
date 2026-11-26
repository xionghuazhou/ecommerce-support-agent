# backend/app/services/logistics_service.py
"""真实联网物流查询服务：快递100 免密接口（单号自动识别 + 官方轨迹查询）"""
from typing import Dict, Any, List

import httpx

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

AUTO_NUMBER_URL = 'https://www.kuaidi100.com/autonumber/autoComNum'
QUERY_URL = 'https://www.kuaidi100.com/query'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    'Referer': 'https://www.kuaidi100.com/',
}

CARRIER_NAMES = {
    'shunfeng': '顺丰速运', 'yuantong': '圆通速递', 'zhongtong': '中通快递',
    'shentong': '申通快递', 'yunda': '韵达快递', 'jd': '京东物流',
    'ems': '中国邮政EMS', 'youzhengguonei': '邮政快递包裹', 'debangwuliu': '德邦物流',
    'debangkuaidi': '德邦快递', 'jtexpress': '极兔速递', 'huitongkuaidi': '百世快递',
    'tiantian': '天天快递', 'youshuwuliu': '优速物流', 'annengwuliu': '安能物流',
    'zhaijibian': '宅急送', 'usci': '邮政标快',
}

STATE_NAMES = {
    '0': '在途', '1': '已揽收', '2': '疑难件', '3': '已签收',
    '4': '已退签', '5': '派件中', '6': '已退回', '7': '转投',
}

# 单号前缀 -> 快递公司编码（autonumber 识别失败时的兜底，如京东子单号 JDX 开头）
PREFIX_CARRIERS = [
    ('SF', 'shunfeng'), ('JDX', 'jd'), ('JDV', 'jd'), ('JD', 'jd'),
    ('JT', 'jtexpress'), ('YT', 'yuantong'), ('ZTO', 'zhongtong'),
    ('STO', 'shentong'), ('YD', 'yunda'), ('EMS', 'ems'), ('DB', 'debangkuaidi'),
]


async def track_express(number: str) -> Dict[str, Any]:
    """实时联网查询快递轨迹。

    返回:
        成功: {'success': True, 'carrier_code', 'carrier_name', 'state_text',
               'trace_text': str, 'trace': [{'time','context'}, ...]}
        失败: {'success': False, 'message': str}
    """
    number = (number or '').strip().replace(' ', '').upper()
    if not number:
        return {'success': False, 'message': '请提供快递单号'}

    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            # 1. 单号自动识别快递公司（可能返回多个候选）
            resp = await client.get(AUTO_NUMBER_URL, params={'text': number})
            resp.raise_for_status()
            candidates: List[str] = [
                item.get('comCode') for item in resp.json().get('auto', []) if item.get('comCode')
            ]
            # 单号前缀兜底识别（JDX 等子品牌单号 autonumber 可能识别不出）
            if not candidates:
                for prefix, code in PREFIX_CARRIERS:
                    if number.startswith(prefix):
                        candidates = [code]
                        logger.info(f'单号 {number} 按前缀 {prefix} 识别为 {code}')
                        break
            if not candidates:
                return {'success': False,
                        'message': f'无法识别单号 {number} 对应的快递公司，请确认单号是否正确。'}

            # 2. 逐个候选查询官方轨迹
            for com_code in candidates[:3]:
                resp = await client.get(QUERY_URL, params={'type': com_code, 'postid': number})
                resp.raise_for_status()
                result = resp.json()

                if str(result.get('status')) != '200':
                    continue

                data: List[Dict[str, str]] = result.get('data') or []
                if not data or any('查无结果' in (d.get('context') or '') for d in data):
                    suffix = ''
                    if com_code == 'shunfeng':
                        suffix = '（顺丰部分单号需提供收件人手机后4位才能查询）'
                    return {
                        'success': False,
                        'message': (f'快递官方（{CARRIER_NAMES.get(com_code, com_code)}）暂时查不到单号 {number} 的轨迹记录，'
                                    f'可能是单号尚未揽收录入、已过期、属于隐私虚拟单号，或单号本身不正确。{suffix}'),
                    }

                carrier_name = CARRIER_NAMES.get(com_code, com_code)
                state_text = STATE_NAMES.get(str(result.get('state')), '在途')

                # 轨迹（快递100 返回最新在前，取前 8 条）
                trace = [{'time': d.get('ftime') or d.get('time', ''),
                          'context': (d.get('context') or '').strip()} for d in data if d.get('context')]
                lines = [f"[{t['time']}] {t['context']}" for t in trace[:8]]
                if len(trace) > 8:
                    lines.append(f'（仅显示最近 8 条，共 {len(trace)} 条）')

                return {
                    'success': True,
                    'carrier_code': com_code,
                    'carrier_name': carrier_name,
                    'state_text': state_text,
                    'trace_text': '\n'.join(lines),
                    'trace': trace,
                }

            tried = '、'.join(CARRIER_NAMES.get(c, c) for c in candidates[:3])
            return {'success': False,
                    'message': f'已按 {tried} 查询，均查不到单号 {number} 的轨迹记录，请核对单号是否正确。'}
    except httpx.TimeoutException:
        logger.warning(f'物流查询超时: {number}')
        return {'success': False, 'message': '物流查询请求超时，请稍后再试。'}
    except Exception as e:
        logger.error(f'物流查询失败: {number}, {e}')
        return {'success': False, 'message': f'物流查询出现异常：{e}'}
