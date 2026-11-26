# backend/app/services/web_search_service.py
"""真实联网搜索服务：必应中国（免密，HTML 解析）"""
import re
from typing import Dict, Any, List, Optional

import httpx

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

SEARCH_URL = 'https://cn.bing.com/search'

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'),
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


def _strip_tags(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()


# 口语/时间/疑问词清洗：整句自然语言直接丢给搜索引擎会得到无关结果
# （如"今天天津南开区天气如何"被必应理解为"今天"而返回黄历日历），
# 清洗后只留核心关键词："天津南开区天气"
_NOISE_PATTERN = re.compile(
    r'今天|今日|现在|目前|当前|此刻|最新|最近|请问|帮我|麻烦|麻烦你|'
    r'查看|查一下|查询|搜索|搜一下|告诉我|一下|如何|怎样|怎么样|什么|吗|呢|了|吧'
)


def _clean_query(query: str) -> str:
    cleaned = _NOISE_PATTERN.sub('', query).strip()
    return cleaned or query


def _query_grams(query: str) -> set:
    """查询词的 2 字滑窗 + 英文数字段（用于结果相关度评分）"""
    grams = set()
    for seg in re.findall(r'[A-Za-z0-9]+|[\u4e00-\u9fff]+', query):
        if seg.isascii():
            grams.add(seg.lower())
        else:
            for i in range(len(seg) - 1):
                grams.add(seg[i:i + 2])
    return grams


def _relevance_score(results: List[Dict[str, str]], grams: set) -> int:
    """结果集与查询的相关度：任一条目的 标题+摘要 命中的 gram 数取最大值"""
    best = 0
    for r in results:
        text = r['title'] + ' ' + r['snippet']
        score = sum(1 for g in grams if g in text)
        best = max(best, score)
    return best


# WMO 天气代码 -> 中文描述
WEATHER_CODES = {
    0: '晴', 1: '大致晴朗', 2: '局部多云', 3: '阴天',
    45: '雾', 48: '雾凇',
    51: '轻毛毛雨', 53: '毛毛雨', 55: '浓毛毛雨',
    61: '小雨', 63: '中雨', 65: '大雨', 66: '冻雨', 67: '冻雨',
    71: '小雪', 73: '中雪', 75: '大雪', 77: '雪粒',
    80: '阵雨', 81: '阵雨', 82: '强阵雨', 85: '阵雪', 86: '阵雪',
    95: '雷阵雨', 96: '雷阵雨伴冰雹', 99: '雷阵雨伴冰雹',
}


async def _weather_lookup(location: str) -> Optional[Dict[str, str]]:
    """Open-Meteo 免费气象 API：地理编码 + 实时天气（数值级真实数据）。

    必应有机搜索结果只有天气门户页链接、没有实时气温，天气类问题优先走这里。
    位置匹配失败时逐级降级：全名 → 去行政区后缀 → 前两/三字。
    """
    candidates: List[str] = []
    for cand in (location, location.replace('市', ''), location.rstrip('区市县'),
                 location[:2], location[:3]):
        cand = cand.strip()
        if cand and cand not in candidates:
            candidates.append(cand)

    async with httpx.AsyncClient(timeout=10) as client:
        for cand in candidates:
            try:
                geo = (await client.get('https://geocoding-api.open-meteo.com/v1/search',
                                        params={'name': cand, 'count': 1, 'language': 'zh'})).json()
                g = (geo.get('results') or [None])[0]
                if not g:
                    continue
                w = (await client.get('https://api.open-meteo.com/v1/forecast', params={
                    'latitude': g['latitude'], 'longitude': g['longitude'],
                    'current_weather': 'true',
                    'daily': 'temperature_2m_max,temperature_2m_min',
                    'forecast_days': 1, 'timezone': 'auto'})).json()
                cw = w.get('current_weather') or {}
                if not cw:
                    continue

                desc = WEATHER_CODES.get(cw.get('weathercode'), '未知')
                name = g.get('name', cand)
                admin1 = g.get('admin1') or ''
                title = f'{admin1} {name} 实时天气' if admin1 and admin1 != name else f'{name} 实时天气'
                snippet = (f"{desc}，当前气温 {cw.get('temperature')}°C，"
                           f"风速 {cw.get('windspeed')} km/h")
                daily = w.get('daily') or {}
                tmax = (daily.get('temperature_2m_max') or [None])[0]
                tmin = (daily.get('temperature_2m_min') or [None])[0]
                if tmax is not None and tmin is not None:
                    snippet += f"；今日气温 {tmin}~{tmax}°C"
                snippet += f"（观测时间 {cw.get('time', '')}）"
                logger.info(f'天气查询成功: {title} -> {snippet}')
                return {'title': title, 'url': 'https://open-meteo.com', 'snippet': snippet}
            except Exception as e:
                logger.warning(f'天气查询候选「{cand}」失败: {e}')
    return None


async def _search_once(query: str, top_k: int) -> List[Dict[str, str]]:
    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        # 注意：params 会自动做 URL 编码，这里不要再手动 quote_plus（否则双重编码变成乱码）
        resp = await client.get(SEARCH_URL, params={'q': query, 'mkt': 'zh-CN'})
        resp.raise_for_status()
        html = resp.text

    results: List[Dict[str, str]] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', html, re.DOTALL):
        if len(results) >= top_k:
            break
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not m:
            continue
        url = m.group(1)
        title = _strip_tags(m.group(2))
        sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        snippet = _strip_tags(sm.group(1))[:220] if sm else ''
        if title:
            results.append({'title': title, 'url': url, 'snippet': snippet})
    return results


async def web_search(query: str, top_k: int = 5) -> Dict[str, Any]:
    """联网搜索，返回 {'success', 'query', 'results': [{title, url, snippet}], 'message'}

    必应对同一意思的不同措辞返回质量差异很大（如"天津南开区天气预报"返回泛页面，
    "南开区天气预报"返回精准结果），因此对清洗后的查询尝试多个变体，取相关度最高的一组。
    """
    query = (query or '').strip()
    if not query:
        return {'success': False, 'results': [], 'message': '缺少搜索关键词'}

    cleaned = _clean_query(query)

    # 天气类问题优先走气象 API（数值级真实数据，比搜索页摘要可靠）
    if '天气' in cleaned:
        location = cleaned.replace('天气预报', '').replace('天气', '').strip(' ，,的')
        if location:
            w = await _weather_lookup(location)
            if w:
                return {'success': True, 'query': query, 'results': [w], 'message': ''}

    # 查询变体：原样 → 天气词规范化 → 去掉开头的行政区划前缀
    variants = [cleaned]
    if '天气预报' in cleaned:
        variants.append(cleaned.replace('天气预报', '天气'))
    if '天气' in cleaned:
        variants.append(cleaned.replace('天气', '天气预报'))
        if len(cleaned) > 4:
            variants.append(cleaned[2:])
    seen = set()
    variants = [v for v in variants if not (v in seen or seen.add(v))]

    grams = _query_grams(cleaned)
    best_results: List[Dict[str, str]] = []
    best_score = -1
    for v in variants:
        try:
            results = await _search_once(v, top_k)
        except Exception as e:
            logger.warning(f'搜索变体「{v}」失败: {e}')
            continue
        if not results:
            continue
        score = _relevance_score(results, grams)
        logger.info(f'联网搜索「{v}」: {len(results)} 条, 相关度 {score}')
        if score > best_score:
            best_score, best_results = score, results
        if best_score >= 3:  # 相关度足够，不再尝试更多变体
            break

    if not best_results:
        return {'success': False, 'results': [],
                'message': f'联网搜索「{query}」没有返回结果，请换个说法再试。'}

    logger.info(f'联网搜索「{query}」完成，最佳相关度 {best_score}')
    return {'success': True, 'query': query, 'results': best_results, 'message': ''}
