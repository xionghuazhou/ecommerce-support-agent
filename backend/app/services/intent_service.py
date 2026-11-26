# backend/app/services/intent_service.py
"""意图识别服务：关键词匹配 + 语义匹配（Embedding）+ LLM 理解，多策略融合"""
import json
import re
from typing import Optional, List

import numpy as np

from app.schemas.intent import IntentResult, Entity
from app.services.llm_service import llm_service
from app.services.embedding_service import embedding_service
from app.core.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class IntentService:
    """意图识别服务"""

    # 预定义意图配置，语义/LLM 兜底覆盖更多意图
    INTENT_CONFIGS = {
        'product_inquiry': {
            'intent_name': '商品咨询', 'handler': 'rag', 'priority': 5,
            'keywords': ['商品', '产品', '多少钱', '价格', '怎么样', '好不好', '有货吗', '库存'],
        },
        'order_query': {
            'intent_name': '订单查询', 'handler': 'tool', 'priority': 8,
            'keywords': ['订单', '查订单', '什么时候到', '发货没', '物流', '快递', '到哪了'],
        },
        'refund_request': {
            'intent_name': '退款退货', 'handler': 'tool', 'priority': 10,
            'keywords': ['退款', '退货', '取消订单', '不想要了', '退钱', '撤单'],
        },
        'complaint': {
            'intent_name': '投诉', 'handler': 'transfer', 'priority': 10,
            'keywords': ['投诉', '差评', '太差了', '骗子', '态度差'],
        },
        'human_agent': {
            'intent_name': '人工客服', 'handler': 'transfer', 'priority': 10,
            'keywords': ['人工', '真人', '转人工', '人工服务', '客服人员'],
        },
        'promotion': {
            'intent_name': '促销活动', 'handler': 'rag', 'priority': 4,
            'keywords': ['促销', '活动', '打折', '优惠', '满减', '折扣'],
        },
        'coupon': {
            'intent_name': '优惠券使用', 'handler': 'rag', 'priority': 4,
            'keywords': ['优惠券', '券', '红包', '抵扣'],
        },
        'shipping': {
            'intent_name': '配送时效', 'handler': 'rag', 'priority': 5,
            'keywords': ['配送', '运费', '几天到', '包邮', '发货时间'],
        },
        'payment': {
            'intent_name': '支付问题', 'handler': 'rag', 'priority': 6,
            'keywords': ['支付', '付款', '微信支付', '支付宝', '货到付款', '发票'],
        },
        'after_sale': {
            'intent_name': '售后政策', 'handler': 'rag', 'priority': 6,
            'keywords': ['售后', '保修', '维修', '质量', '坏了', '七天无理由'],
        },
        'member': {
            'intent_name': '会员权益', 'handler': 'rag', 'priority': 3,
            'keywords': ['会员', '积分', '等级', '权益'],
        },
        'greeting': {
            'intent_name': '问候', 'handler': 'llm', 'priority': 1,
            'keywords': ['你好', '您好', 'hi', 'hello', '在吗', '谢谢', '感谢', '辛苦了', '再见', '拜拜'],
        },
    }

    # 意图编码 -> 工具映射（handler=tool 时使用）
    INTENT_TOOL_MAP = {
        'order_query': 'query_order',
        'order_modify': 'query_order',
        'cancel_order': 'refund',
        'refund_request': 'refund',
        'logistics_track': 'track_logistics',
        'urge_shipping': 'query_order',
        'modify_address': 'query_order',
        'product_inquiry': 'query_product',
    }

    # 意图编码 -> 快捷回复
    QUICK_REPLIES = {
        'order_query': ['查一下我的全部订单', '物流到哪了', '什么时候发货'],
        'refund_request': ['退款进度查询', '退货流程是什么', '取消订单'],
        'product_inquiry': ['有什么促销活动', '推荐热销商品', '查询库存'],
        'promotion': ['优惠券怎么领', '满减活动有哪些', '会员日优惠'],
        'human_agent': ['描述我的问题', '创建工单'],
    }

    # LLM 允许输出的意图编码白名单（防止小模型编造不存在的意图码）
    VALID_LLM_INTENT_CODES = set(INTENT_CONFIGS.keys()) | {
        'order_modify', 'cancel_order', 'logistics_track', 'urge_shipping',
        'modify_address', 'refund_dispute',
    }

    # 纯寒暄词：命中时高置信度归类为问候
    CHAT_EXACT = {'你好', '您好', '在吗', 'hi', 'hello', '谢谢', '感谢', '辛苦了', '再见'}

    # 政策咨询类问句特征（出现时不应触发退款/取消等动作型工具）
    POLICY_PATTERN = re.compile(r'政策|流程|规则|条件|标准|是什么|什么意思|多久|几天|怎么退|如何退|怎么申请|如何申请')
    ACTION_PATTERN = re.compile(r'我要|给我|申请一下|取消|办理|投诉|不想要了|退钱|退我')

    def __init__(self):
        # 示例语料向量缓存（由外部调用 build_semantic_index 填充）
        self._utterance_matrix: np.ndarray | None = None
        self._utterance_labels: list[tuple[str, str, str, int]] = []  # (intent_code, name, handler, priority)

    async def recognize(self, text: str, user_id: Optional[int] = None) -> IntentResult:
        """识别用户意图：关键词 -> 语义 -> LLM -> 融合 -> 实体抽取"""
        logger.info(f'开始意图识别: {text}')

        keyword_intent = self._keyword_match(text)
        semantic_intent = await self._semantic_match(text)
        llm_intent = await self._llm_understand(text)

        final_intent = self._fuse_intents(keyword_intent, semantic_intent, llm_intent)

        # 政策咨询保护：问"政策/流程/是什么"时不触发订单/退款等动作型工具，改走 RAG
        if (final_intent.intent_code in ('refund_request', 'cancel_order', 'refund_dispute', 'order_query')
                and self.POLICY_PATTERN.search(text)
                and not self.ACTION_PATTERN.search(text)):
            final_intent = IntentResult(
                intent_code='after_sale', intent_name='售后政策',
                confidence=max(0.6, final_intent.confidence - 0.1),
                handler_type='rag', priority=6, source='fuse',
            )

        # 快递单号优先路由：消息里带运单号（且非 ORDER 订单号）时直接判定为物流追踪
        cleaned_text = re.sub(r'\s+', '', text)
        if not re.search(r'ORDER\d{6,}', cleaned_text, re.IGNORECASE):
            for cand in re.findall(r'[A-Za-z]{1,4}\d{9,}|\d{12,}', cleaned_text):
                if re.fullmatch(r'1[3-9]\d{9}', cand):  # 排除手机号
                    continue
                logger.info(f'检测到快递运单号 {cand}，直接路由到物流追踪')
                return IntentResult(
                    intent_code='logistics_track', intent_name='物流追踪',
                    confidence=0.85,
                    entities=[Entity(type='tracking_no', value=cand.upper())],
                    handler_type='tool', priority=9, source='fuse',
                )

        final_intent.entities = self._extract_entities(text)

        logger.info(f'意图识别完成: {final_intent.intent_code} (confidence={final_intent.confidence:.2f}, '
                    f'source={getattr(final_intent, "source", "unknown")})')
        return final_intent

    def _keyword_match(self, text: str) -> Optional[IntentResult]:
        """关键词匹配"""
        text_lower = text.lower()
        best: Optional[IntentResult] = None

        for intent_code, config in self.INTENT_CONFIGS.items():
            for keyword in config['keywords']:
                if keyword.lower() in text_lower:
                    # 纯寒暄词（谢谢/你好等）给高置信度，避免被低质语义匹配抢走
                    confidence = 0.9 if keyword in self.CHAT_EXACT else 0.7
                    result = IntentResult(
                        intent_code=intent_code,
                        intent_name=config['intent_name'],
                        confidence=confidence,
                        entities=[],
                        handler_type=config['handler'],
                        priority=config['priority'],
                        source='keyword',
                    )
                    if best is None or config['priority'] > best.priority:
                        best = result
        return best

    async def _semantic_match(self, text: str) -> Optional[IntentResult]:
        """语义匹配：与意图示例语料算余弦相似度"""
        if self._utterance_matrix is None or not len(self._utterance_labels):
            return None
        try:
            query_vec = await embedding_service.embed_one(text)
            sims = self._utterance_matrix @ query_vec
            best_idx = int(np.argmax(sims))
            best_score = float(sims[best_idx])
            if best_score < settings.INTENT_THRESHOLD:
                return None
            code, name, handler, priority = self._utterance_labels[best_idx]
            result = IntentResult(
                intent_code=code, intent_name=name, confidence=round(0.5 + best_score * 0.4, 4),
                entities=[], handler_type=handler, priority=priority, source='semantic',
            )
            return result
        except Exception as e:
            logger.warning(f'语义匹配失败: {e}')
            return None

    async def build_semantic_index_async(self, samples: list[tuple[str, str, str, str, int]]):
        """构建示例语料向量索引（启动时调用）。samples: (utterance, intent_code, name, handler, priority)"""
        """异步构建示例语料索引（启动时调用）"""
        if not samples:
            return
        texts = [s[0] for s in samples]
        self._utterance_matrix = await embedding_service.embed(texts)
        self._utterance_labels = [(s[1], s[2], s[3], s[4]) for s in samples]
        logger.info(f'意图语义索引构建完成，共 {len(samples)} 条示例语料')

    async def _llm_understand(self, text: str) -> Optional[IntentResult]:
        """LLM 深度理解（LLM 不可用时跳过，不影响整体流程）"""
        if not llm_service.is_available:
            return None
        prompt = f"""分析用户输入的意图。

用户输入：{text}

可选意图：product_inquiry, order_query, refund_request, complaint, human_agent, greeting, promotion, payment, shipping, other

只输出一行 JSON，严格按此示例格式，不要输出任何其他文字：
{{"intent_code": "order_query", "confidence": 0.9}}"""

        response = await llm_service.generate(prompt, temperature=0.1, json_mode=True)
        if response is None:
            return None

        # 宽松解析：先试标准 JSON，失败再用正则逐字段提取（小模型常输出残缺 JSON）
        code: Optional[str] = None
        confidence = 0.5
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                code = result.get('intent_code')
                confidence = float(result.get('confidence', 0.5) or 0.5)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        if not code:
            code_match = re.search(r'"intent_code"\s*:\s*"([A-Za-z_]+)"', response)
            if code_match:
                code = code_match.group(1)
                conf_match = re.search(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)', response)
                if conf_match:
                    try:
                        confidence = float(conf_match.group(1))
                    except ValueError:
                        pass
        if not code:
            return None
        code = code.lower()
        # 白名单校验：小模型编造的不存在的意图码（如 dimensioned_query）一律拒绝
        if code in ('other', 'fallback') or code not in self.VALID_LLM_INTENT_CODES:
            logger.warning(f'LLM 返回未知意图码 {code}，已拒绝，改用关键词/语义匹配结果')
            return None
        if not (0.0 < confidence <= 1.0):
            confidence = 0.5

        known = self.INTENT_CONFIGS.get(code)
        return IntentResult(
            intent_code=code,
            intent_name=known['intent_name'] if known else code,
            confidence=confidence,
            entities=[],
            handler_type=known['handler'] if known else 'llm',
            priority=known['priority'] if known else 5,
            source='llm',
        )

    def _fuse_intents(self, *intents) -> IntentResult:
        """多策略融合：置信度为主、优先级为辅（eff = confidence + priority*0.03），全空则 fallback"""
        valid_intents = [i for i in intents if i is not None]

        if not valid_intents:
            return IntentResult(
                intent_code='fallback', intent_name='其他', confidence=0.4,
                entities=[], handler_type='llm', priority=0, source='fuse'
            )

        best = max(valid_intents, key=lambda i: i.confidence + i.priority * 0.03)
        best.source = best.source or 'fuse'
        return best

    def _extract_entities(self, text: str) -> List[Entity]:
        """规则实体抽取：order_no / phone / price / date"""
        entities: List[Entity] = []

        for match in re.finditer(r'ORDER\s?\d{6,}', text, re.IGNORECASE):
            value = match.group().replace(' ', '').upper()
            entities.append(Entity(type='order_no', value=value, start=match.start(), end=match.end()))

        for match in re.finditer(r'(?<!\d)1[3-9]\d{9}(?!\d)', text):
            entities.append(Entity(type='phone', value=match.group(), start=match.start(), end=match.end()))

        for match in re.finditer(r'[¥￥]?\s?\d+(\.\d{1,2})?\s?元', text):
            entities.append(Entity(type='price', value=match.group().strip(), start=match.start(), end=match.end()))

        for match in re.finditer(r'(\d{1,2}月\d{1,2}[日号]|今天|明天|后天|昨天|上周|上周\d)', text):
            entities.append(Entity(type='date', value=match.group(), start=match.start(), end=match.end()))

        return entities


# 全局单例
intent_service = IntentService()
