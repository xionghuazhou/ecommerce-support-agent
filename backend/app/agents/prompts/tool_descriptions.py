# backend/app/agents/prompts/tool_descriptions.py
"""工具描述（用于 LLM 工具调用）"""

TOOL_DESCRIPTIONS = """
## 🔧 可用工具

### 1. search_knowledge（知识库检索）
- 用途：从平台知识库检索商品信息、平台政策、常见问题解答
- 输入：搜索关键词
- 输出：相关的知识库条目
- 示例：用户问"退换货政策"，调用此工具

### 2. query_order（订单查询）
- 用途：查询用户订单的状态、物流、收货信息
- 输入：订单号（可选，不提供则返回订单列表）
- 输出：订单详细信息或订单列表
- 示例：用户问"我的订单什么时候到"，调用此工具

### 3. query_product（商品查询）
- 用途：搜索商品、了解价格库存、查看促销
- 输入：商品关键词
- 输出：商品列表及价格库存信息
- 示例：用户问"iPhone有优惠吗"，调用此工具

### 4. refund（退款退货）
- 用途：处理取消订单、退款申请、退货流程
- 输入：操作类型（cancel/return/refund/query）、订单号、原因
- 输出：操作结果和处理流程
- 示例：用户说"我要退款"，调用此工具

### 5. transfer_human（转人工）
- 用途：将用户转接给人工客服
- 输入：转接原因
- 输出：转接状态和等待时间
- 示例：用户明确要求转人工，或遇到复杂问题时调用

### 6. create_ticket（创建工单）
- 用途：记录用户问题，生成工单待处理
- 输入：工单类型、标题、内容
- 输出：工单编号
- 示例：用户反馈问题但暂时无法解决时调用

### 7. track_logistics（快递轨迹实时查询·真实联网）
- 用途：通过快递100 实时查询任意快递单号的官方物流轨迹（顺丰/圆通/中通/京东/EMS/极兔等）
- 输入：快递运单号
- 输出：快递公司、当前状态、最新轨迹列表
- 示例：用户提供快递单号（如 SF1392690203975）要求查物流时调用

### 8. web_search（联网搜索·真实联网）
- 用途：实时联网搜索知识库之外、需要最新信息的问题（新闻、天气、赛事、行情、外部常识等）
- 输入：搜索关键词
- 输出：网页标题、摘要与来源链接
- 示例：用户问"今天上海天气怎么样"、"最近有什么新品发布"时调用；回答时注明信息来自联网搜索
"""

TOOL_JSON_SCHEMA = [
    {
        "name": "search_knowledge",
        "description": "从知识库中检索商品信息、平台政策、常见问题等",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "category": {"type": "string", "description": "知识库分类（可选）"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "query_order",
        "description": "查询用户订单状态、物流信息、收货地址等",
        "parameters": {
            "type": "object",
            "properties": {
                "order_no": {"type": "string", "description": "订单号（可选）"}
            },
            "required": []
        }
    },
    {
        "name": "query_product",
        "description": "搜索商品信息、价格、库存",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {"type": "string", "description": "商品关键词"},
                "category": {"type": "string", "description": "商品分类"}
            },
            "required": ["keywords"]
        }
    },
    {
        "name": "refund",
        "description": "处理退款退货申请、取消订单",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["cancel", "return", "refund", "query"],
                    "description": "操作类型"
                },
                "order_no": {"type": "string", "description": "订单号"},
                "reason": {"type": "string", "description": "原因"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "transfer_human",
        "description": "将用户转接给人工客服",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": ["用户主动请求", "投诉", "技术问题", "其他"],
                    "description": "转接原因"
                }
            },
            "required": ["reason"]
        }
    },
    {
        "name": "create_ticket",
        "description": "创建客服工单",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["complaint", "refund", "consult", "suggestion"],
                    "description": "工单类型"
                },
                "title": {"type": "string", "description": "工单标题"},
                "content": {"type": "string", "description": "工单内容"}
            },
            "required": ["type", "content"]
        }
    },
    {
        "name": "track_logistics",
        "description": "实时联网查询快递单号的官方物流轨迹（支持顺丰/圆通/中通/京东/EMS/极兔等）",
        "parameters": {
            "type": "object",
            "properties": {
                "tracking_no": {"type": "string", "description": "快递运单号，如 SF1392690203975"}
            },
            "required": ["tracking_no"]
        }
    },
    {
        "name": "web_search",
        "description": "实时联网搜索最新信息（新闻、天气、行情、外部常识等）",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    }
]
