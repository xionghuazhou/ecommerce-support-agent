# backend/app/agents/customer_agent.py
"""电商客服 Agent - 基于 ReAct 架构

处理流程：
用户消息 -> 消息预处理 -> 情感分析 -> NLU 意图识别 -> 按处理器类型路由
  (rag: RAG 检索 + LLM 生成 | tool: ReAct 循环调用工具 | transfer: 转人工 | llm: LLM 直接回复)
-> LLM 整合输出 -> 返回结果
"""
import json
import re
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.agents.prompts.system_prompt import get_system_prompt
from app.agents.prompts.tool_descriptions import TOOL_DESCRIPTIONS, TOOL_JSON_SCHEMA
from app.agents.tools import (SearchKnowledgeTool, QueryOrderTool, QueryProductTool,
                              RefundTool, TransferHumanTool, CreateTicketTool, TrackLogisticsTool,
                              WebSearchTool)
from app.services.intent_service import intent_service
from app.services.sentiment_service import SentimentService, SentimentType, sentiment_service
from app.services.rag_service import rag_service
from app.services.llm_service import llm_service
from app.core.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# 模型偶尔用中文键名传参（如 "订单号"），统一映射回工具定义的英文参数名
PARAM_KEY_ALIASES = {
    '订单号': 'order_no', '订单编号': 'order_no', '订单': 'order_no',
    '关键词': 'keywords', '查询': 'query', '搜索': 'query',
    '原因': 'reason', '类型': 'type', '标题': 'title', '内容': 'content',
    '操作': 'action', '分类': 'category', '类别': 'category',
    '物流单号': 'tracking_no', '快递单号': 'tracking_no', '运单号': 'tracking_no', '单号': 'tracking_no',
    '搜索词': 'query', '搜索内容': 'query',
}


class CustomerServiceAgent(BaseAgent):
    """电商客服 Agent - 基于 ReAct 架构"""

    def __init__(self, db: AsyncSession, session_id: str, user_id: Optional[int] = None):
        super().__init__(session_id, user_id)
        self.db = db
        self.tools = self._init_tools()

    def _init_tools(self) -> Dict[str, Any]:
        """注册 8 个业务工具（6 个业务工具 + 真实联网快递查询 + 真实联网搜索）"""
        return {
            'search_knowledge': SearchKnowledgeTool(),
            'query_order': QueryOrderTool(),
            'query_product': QueryProductTool(),
            'refund': RefundTool(),
            'transfer_human': TransferHumanTool(),
            'create_ticket': CreateTicketTool(),
            'track_logistics': TrackLogisticsTool(),
            'web_search': WebSearchTool(),
        }

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    async def process_message(self, content: str) -> Dict[str, Any]:
        """处理一条用户消息，返回完整响应信息"""
        # 1. 消息预处理（清洗）
        text = self._preprocess(content)

        # 2. 情感分析
        sentiment, sentiment_score = await sentiment_service.analyze(text)
        strategy = sentiment_service.get_response_strategy(sentiment, sentiment_score)
        self.update_state('last_sentiment', sentiment)

        # 3. NLU 意图识别
        intent = await intent_service.recognize(text, self.user_id)
        self.update_state('last_intent', intent.intent_code)

        # 4. 按处理器类型路由
        handler = intent.handler_type
        tool_trace: List[Dict[str, Any]] = []

        if handler == 'transfer':
            answer, tool_trace, need_transfer = await self._handle_transfer(intent)
        elif handler == 'tool':
            answer, tool_trace = await self._handle_tool(text, intent)
            need_transfer = False
        elif handler == 'rag':
            answer, tool_trace = await self._handle_rag(text, intent)
            need_transfer = False
        else:  # llm / fallback / greeting
            if intent.intent_code == 'fallback' and llm_service.is_available:
                # 兜底问题交给 ReAct：模型可自主决定调用 web_search 联网搜索
                answer, tool_trace = await self._handle_tool(text, intent)
                if answer is None:
                    answer, tool_trace = await self._handle_llm(text)
            else:
                answer, tool_trace = await self._handle_llm(text)
            need_transfer = False

        # 5. 情感策略包装：消极情绪优先安抚
        answer = self._apply_sentiment_strategy(answer, sentiment, sentiment_score)

        # 6. 自动转人工：情感得分低于阈值（情感驱动转人工策略）
        if (sentiment == SentimentType.NEGATIVE
                and sentiment_score <= settings.AUTO_TRANSFER_SENTIMENT_THRESHOLD
                and intent.intent_code != 'human_agent'):
            need_transfer = True

        return {
            'response': answer,
            'intent': intent,
            'sentiment': sentiment,
            'sentiment_score': sentiment_score,
            'quick_replies': intent_service.QUICK_REPLIES.get(intent.intent_code, self._default_quick_replies(intent)),
            'need_transfer': need_transfer,
            'tool_trace': tool_trace,
            'response_strategy': strategy,
        }

    # ------------------------------------------------------------------
    # 处理器
    # ------------------------------------------------------------------
    async def _handle_transfer(self, intent) -> tuple[str, List[Dict], bool]:
        """转人工"""
        reason = '投诉' if intent.intent_code == 'complaint' else '用户主动请求'
        result = await self.tools['transfer_human'].execute({
            'session_id': self.session_id, 'user_id': self.user_id, 'reason': reason,
        })
        trace = [{'tool': 'transfer_human', 'params': {'reason': reason}, 'result': result.get('response', '')[:200]}]
        return result['response'], trace, True

    async def _handle_tool(self, text, intent) -> tuple[str, List[Dict]]:
        """工具类意图：优先 ReAct 循环（LLM 决策），LLM 不可用时规则直调"""
        if llm_service.is_available:
            answer, trace = await self._react_loop(text, intent)
            if answer is not None:
                return answer, trace
        # 规则兜底：按意图映射直接调用工具
        return await self._rule_dispatch(text, intent)

    async def _handle_rag(self, text, intent=None) -> tuple[str, List[Dict]]:
        """RAG 检索 + LLM 生成"""
        hits = await rag_service.search(text)
        trace = [{'tool': 'search_knowledge',
                  'params': {'query': text[:50]},
                  'result': f'命中 {len(hits)} 条知识'}]

        # 弱命中（相关度不足）视为未命中，避免答非所问
        if hits and hits[0]['score'] < 0.55:
            hits = []

        if not hits:
            # 知识库未命中：转 ReAct 并解除指定工具限制，模型可自主决定 web_search 联网搜索
            if llm_service.is_available:
                fb_intent = intent.model_copy(update={'intent_code': 'fallback', 'intent_name': '其他'})
                answer, trace2 = await self._handle_tool(text, fb_intent)
                if answer is not None:
                    return answer, trace2
            return await self._handle_llm(text)

        # 高置信度命中：直接返回知识原文（避免小模型改写价格/条款等关键数字）
        top = hits[0]
        second_gap = (top['score'] - hits[1]['score']) if len(hits) > 1 else 1.0
        if top['score'] >= 0.70 and second_gap >= 0.03:
            trace[0]['result'] = f"高置信命中（{top['score']:.0%}），返回知识原文"
            return top['answer'], trace

        context = '\n\n'.join(
            f"[{i}]（{h['category']}）问：{h['question']}\n答：{h['answer']}"
            for i, h in enumerate(hits, 1)
        )

        if llm_service.is_available:
            prompt = f"""请根据以下知识库内容回答用户问题。严格要求：
1. 只使用知识库中的信息，不要编造知识库里没有的内容
2. 知识库中出现的数字（价格、天数、金额、比例等）必须原样引用，一个字符都不能改
3. 如果知识库内容不足以回答，请如实说明并建议用户转人工

## 知识库检索结果
{context}

## 用户问题
{text}

请用简洁友好的中文回答（200字以内），可直接整合多条知识。"""
            answer = await llm_service.generate(prompt, system_prompt=get_system_prompt(), temperature=0.3)
            if answer:
                # 数字一致性校验：LLM 改写了知识库数字时回退知识原文
                evidence = f'{text}\n{context}'
                numbers = re.findall(r'\d+(?:\.\d+)?', answer)
                if any(n not in evidence for n in numbers):
                    logger.warning(f'RAG 回复数字失真，回退知识原文: {numbers}')
                    return top['answer'], trace
                return answer, trace

        # LLM 不可用：直接返回最相关知识原文（模板兜底）
        best = hits[0]
        return best['answer'], trace

    async def _handle_llm(self, text) -> tuple[str, List[Dict]]:
        """LLM 直接回复（问候/兜底）"""
        if llm_service.is_available:
            hits = await rag_service.search(text, top_k=2)
            context = ''
            if hits:
                context = '\n\n可参考的知识：\n' + '\n'.join(
                    f"- （{h['category']}）{h['question']}：{h['answer'][:120]}" for h in hits)

            messages = [{'role': 'system', 'content': get_system_prompt() + context}]
            messages.extend(self.conversation_history[-8:])
            messages.append({'role': 'user', 'content': text})
            answer = await llm_service.chat(messages, temperature=0.7)
            if answer:
                self.add_history('user', text)
                self.add_history('assistant', answer)
                return answer, []

        # 模板兜底（无 LLM 时保证可用）
        return self._template_reply(text), []

    # ------------------------------------------------------------------
    # ReAct 循环（ReAct 决策流程：Thought -> Action -> Observation -> ... -> Final Answer）
    # ------------------------------------------------------------------
    async def _react_loop(self, user_message, intent) -> tuple[Optional[str], List[Dict]]:
        max_iter = settings.AGENT_MAX_ITERATIONS
        trace: List[Dict[str, Any]] = []
        called_any = False   # 是否真实调用过工具（防止模型跳过工具直接编造）
        last_sig = None      # 上一轮调用签名（防重复空转）
        dup_count = 0

        system = get_system_prompt() + '\n' + TOOL_DESCRIPTIONS + """
## 📐 输出格式（严格遵守）
需要调用工具时输出（三行，缺一不可）：
Thought: <你的推理，一句话>
Action: <工具名，必须是可用工具之一>
Action Input: <JSON 参数，合法 JSON>

信息足够回答时输出：
Final Answer: <给用户的最终回复>

注意：每次回复只能包含上述一种格式，不要同时输出多种。
- Action Input 必须使用「已知信息」里给出的参数原值（尤其是订单号，禁止改写任何数字）
- Action Input 的键名必须用英文（如 order_no、keywords、query、reason），禁止用中文键名
- 用户没有提供订单号时不要编造，Action Input 用空对象 {{}} 即可
- Final Answer 只能陈述 Observation 中出现的事实，禁止编造订单状态、金额、物流信息"""

        # 注入实体与建议动作，帮小模型把参数填对
        entity_lines = []
        for e in intent.entities:
            entity_lines.append(f'- {e.type} = {e.value}')
        suggested_tool = intent_service.INTENT_TOOL_MAP.get(intent.intent_code)
        if suggested_tool:
            hint_lines = [f'本轮任务：用户的意图是「{intent.intent_name}」，你必须调用 {suggested_tool} 工具来处理（不要调用其他工具）。']
        else:
            hint_lines = ['本轮任务：无固定工具。若问题需要最新信息或你不确定的事实（天气、新闻、行情、外部常识等），'
                          '先调用 web_search 联网搜索再回答；若与本商城政策/商品相关，调用 search_knowledge；'
                          '都无需工具时直接给出 Final Answer。'
                          '注意：即使用户的问题与购物无关（如天气、歌曲、常识），也不要拒绝，'
                          '调用 web_search 搜索后热情地回答用户。']
        if entity_lines:
            hint_lines.append('已知信息（从用户原话提取，参数必须原样使用）：\n' + '\n'.join(entity_lines))
        if suggested_tool == 'refund':
            hint_lines.append('refund 工具的 action 参数按用户诉求选择：取消订单用 cancel，退货用 return，退款用 refund。')
        if suggested_tool in ('query_order', 'refund') and not any(e.type == 'order_no' for e in intent.entities):
            hint_lines.append('用户没有提供订单号：不要编造订单号，Action Input 用空对象 {} 调用，工具会自动返回最近的订单列表。')
        # 用户消息里带的是快递运单号（而非 ORDER 订单号）时，改用真实联网快递查询
        cleaned_msg = user_message.replace(' ', '')
        m_order = re.search(r'ORDER\d{6,}', cleaned_msg, re.IGNORECASE)
        track_match = None
        for cand in re.findall(r'[A-Za-z]{1,4}\d{9,}|\d{12,}', cleaned_msg):
            if re.fullmatch(r'1[3-9]\d{9}', cand):  # 排除手机号
                continue
            if m_order and cand.upper() in m_order.group().upper():  # 排除订单号内嵌数字
                continue
            track_match = cand
            break
        if track_match and suggested_tool in ('query_order', 'track_logistics'):
            hint_lines[0] = ('本轮任务：用户提供了快递运单号，你必须调用 track_logistics 工具实时联网查询物流轨迹'
                             '（不要调用 query_order 或其他工具）。')
            hint_lines.append(f'- tracking_no = {track_match.upper()}')

        first_user = f'用户问题：{user_message}\n（识别意图：{intent.intent_code}，用户ID：{self.user_id}，会话ID：{self.session_id}）'
        if hint_lines:
            first_user += '\n\n' + '\n'.join(hint_lines)

        messages: List[Dict[str, str]] = [{'role': 'system', 'content': system}]
        messages.extend(self.conversation_history[-6:])
        messages.append({'role': 'user', 'content': first_user})

        for iteration in range(max_iter):
            response = await llm_service.chat(messages, temperature=0.2)
            if response is None:
                return None, trace  # LLM 故障，交给规则兜底

            final_answer = self._parse_final_answer(response)
            if final_answer is not None:
                final_answer = self._integrity_check(final_answer, trace)
                final_answer = self._grounded_answer(final_answer, trace, user_message)
                self.add_history('user', user_message)
                self.add_history('assistant', final_answer)
                return final_answer, trace

            action, action_input = self._parse_action(response)
            if action is None:
                # 格式错误：纠正一次，连续失败则放弃 ReAct
                messages.append({'role': 'assistant', 'content': response})
                messages.append({'role': 'user', 'content': '输出格式不正确。请严格按格式输出 Action 和 Action Input，或直接给出 Final Answer。'})
                if iteration >= 1:
                    return None, trace
                continue

            tool = self.tools.get(action)
            if tool is None:
                messages.append({'role': 'assistant', 'content': response})
                messages.append({'role': 'user', 'content': f'工具 {action} 不存在。可用工具：{", ".join(self.tools.keys())}。请重新选择。'})
                continue

            # 执行工具
            tool_params = {'db': self.db, 'session_id': self.session_id,
                           'user_id': self.user_id, 'user_message': user_message}
            if isinstance(action_input, dict):
                tool_params.update(self._normalize_params(action_input))
            result = await tool.execute(tool_params)
            observation = result.get('response', '')
            called_any = True
            trace.append({'tool': action, 'params': action_input or {},
                          'result': observation[:300], 'success': result.get('success'),
                          'tool_response': observation, 'iteration': iteration + 1})
            logger.info(f'ReAct 第{iteration + 1}轮: {action}({json.dumps(action_input, ensure_ascii=False)}) -> {observation[:80]}')

            messages.append({'role': 'assistant', 'content': response})
            messages.append({'role': 'user', 'content': f'Observation: {observation}'})

            # 防重复空转：同一工具+同样参数连续调用时熔断
            sig = (action, json.dumps(self._normalize_params(action_input or {}), ensure_ascii=False, sort_keys=True))
            if sig == last_sig:
                dup_count += 1
                if dup_count >= 2:
                    logger.warning(f'工具 {action} 连续重复调用，熔断 ReAct 循环')
                    break
                messages.append({'role': 'user',
                                 'content': '不要重复调用相同的工具和参数。若缺少必要信息（如快递单号），'
                                            '直接输出 Final Answer 向用户询问；否则基于已有 Observation 给出 Final Answer。'})
            else:
                dup_count = 0
            last_sig = sig

        # 指定了必须调用的工具却全程未调用：视为不可信，转规则直调（由工具产生真实数据）。
        # 兜底问题（suggested_tool 为空）允许模型直接回答，不强制调工具。
        if not called_any and suggested_tool is not None:
            logger.warning('ReAct 循环结束仍未调用任何工具（模型试图跳过工具直接回答），放弃 LLM 结果，转规则直调')
            return None, trace

        # 达到最大轮数：让 LLM 基于已有信息收尾
        messages.append({'role': 'user', 'content': '已达到最大工具调用次数，请根据以上信息直接输出 Final Answer。'})
        response = await llm_service.chat(messages, temperature=0.2)
        answer = self._parse_final_answer(response or '')
        if answer:
            answer = self._integrity_check(answer, trace)
            answer = self._grounded_answer(answer, trace, user_message)
            return answer, trace
        return None, trace

    @staticmethod
    def _integrity_check(answer: str, trace: List[Dict]) -> str:
        """反编造护栏：工具报告失败/未找到，而回复却声称成功时，用 Observation 原文纠正"""
        if not trace:
            return answer
        last_obs = trace[-1].get('result', '')
        failure = any(m in last_obs for m in ('未找到', '请提供', '无法查询', '异常', '失败', '不存在', '不属于'))
        claimed_success = any(m in answer for m in ('成功', '已发货', '已送达', '已退款', '已取消', '已提交'))
        if failure and claimed_success:
            logger.warning(f'拦截编造回复: {answer[:60]}... (Observation: {last_obs[:60]})')
            return f'很抱歉，刚才的处理没有成功：{last_obs[:150]}'
        return answer

    @staticmethod
    def _grounded_answer(answer: str, trace: List[Dict], user_message: str) -> str:
        """数字一致性校验（确定性代码，不依赖模型自觉）。

        小模型改写数字的概率很高（799->715、2026-08-15->226-8-51）。
        回复中出现的每个数字都必须能在「用户原话 + 工具返回」中找到，
        否则视为模型转述失真，直接采用工具生成的原文（本身已是排版好的用户可读文案）。
        """
        if not trace:
            return answer
        evidence = user_message + '\n' + '\n'.join(t.get('tool_response', '') for t in trace)
        numbers = re.findall(r'\d+(?:\.\d+)?', answer)
        bad = [n for n in numbers if n not in evidence]
        if not bad:
            return answer
        logger.warning(f'数字一致性校验失败，回退工具原文。失真数字: {bad}')
        for t in reversed(trace):
            if t.get('success') and t.get('tool_response'):
                return t['tool_response']
        last_obs = trace[-1].get('result', '')
        return f'{last_obs[:200]}' if last_obs else answer

    async def _rule_dispatch(self, text, intent) -> tuple[str, List[Dict]]:
        """规则直调工具（LLM 不可用的兜底路径）"""
        tool_name = intent_service.INTENT_TOOL_MAP.get(intent.intent_code, 'search_knowledge')

        if tool_name == 'search_knowledge':
            return await self._handle_rag(text)

        tool = self.tools.get(tool_name)
        if tool is None:
            return await self._handle_rag(text)

        params: Dict[str, Any] = {'db': self.db, 'session_id': self.session_id,
                                  'user_id': self.user_id, 'user_message': text}
        if tool_name == 'query_product':
            params['keywords'] = self._extract_product_keywords(text)
        elif tool_name == 'refund':
            params['action'] = None  # 让工具按关键词自行判断
        elif tool_name == 'transfer_human':
            params['reason'] = '用户主动请求'

        result = await tool.execute(params)
        trace = [{'tool': tool_name, 'params': {k: v for k, v in params.items() if k not in ('db',)},
                  'result': result.get('response', '')[:300]}]
        return result['response'], trace

    # ------------------------------------------------------------------
    # 解析与工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _preprocess(text: str) -> str:
        """消息预处理：文本清洗 + 格式标准化"""
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """中文键名 -> 英文参数名"""
        return {PARAM_KEY_ALIASES.get(k, k): v for k, v in params.items()}

    @staticmethod
    def _parse_final_answer(response: str) -> Optional[str]:
        match = re.search(r'Final\s?Answer\s*[:：]\s*(.+)', response, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _parse_action(response: str) -> tuple[Optional[str], Optional[Dict]]:
        action_match = re.search(r'Action\s*[:：]\s*(\w+)', response)
        if not action_match:
            return None, None
        action = action_match.group(1)

        input_match = re.search(r'Action\s?Input\s*[:：]\s*(\{.*?\})\s*(?:\n|$)', response, re.DOTALL)
        if input_match:
            try:
                return action, json.loads(input_match.group(1))
            except json.JSONDecodeError:
                pass
        # Action Input 缺失或非法：返回空参数
        return action, {}

    @staticmethod
    def _extract_product_keywords(text: str) -> str:
        """从口语化句子中粗提商品关键词"""
        cleaned = re.sub(r'[吗呢吧？?！!。，,]', '', text)
        for w in ['请问', '我想', '我要', '查询', '查一下', '有没有', '你们', '推荐一下',
                  '推荐', '什么', '怎么样', '多少钱', '价格', '库存', '有货', '购买', '看看']:
            cleaned = cleaned.replace(w, '')
        return cleaned.strip() or text

    def _apply_sentiment_strategy(self, answer: str, sentiment: SentimentType, score: float) -> str:
        """按情感策略包装回复（消极：安抚前缀；积极：热情前缀）"""
        strategy = sentiment_service.get_response_strategy(sentiment, score)
        prefix = strategy.get('prefix', '')
        if not prefix:
            return answer
        # 转人工/工单类消息自带完整话术，不加前缀
        if answer.startswith(('👋', '✅')):
            return answer
        if sentiment == SentimentType.NEGATIVE:
            return f'{prefix}。{answer}' if not answer.startswith(prefix) else answer
        if sentiment == SentimentType.POSITIVE:
            return f'{prefix}！{answer}' if not answer.startswith(prefix) else answer
        return answer

    @staticmethod
    def _default_quick_replies(intent) -> List[str]:
        return ['查一下我的订单', '退换货政策', '有什么优惠活动', '转人工客服']

    def _template_reply(self, text: str) -> str:
        """LLM 不可用时的模板回复"""
        if any(k in text for k in ['你好', '您好', 'hi', 'hello', '在吗']):
            return f'您好！我是智能客服{settings.AGENT_NAME}，很高兴为您服务～请问有什么可以帮到您的？'
        if any(k in text for k in ['谢谢', '感谢']):
            return '不客气，为您服务是我的荣幸～如还有其他问题，随时告诉我！'
        hits_hint = '您可以问我订单、商品、退换货政策等问题，或回复"转人工"接入人工客服。'
        return (f'抱歉，我暂时无法深入理解这个问题（AI 服务未连接）。{hits_hint}')
