# backend/scripts/test_api.py
"""端到端冒烟测试：模拟真实用户对话流程

用法（服务启动后，在 backend 目录下）：
    python scripts/test_api.py
"""
import json
import sys

import httpx

BASE = 'http://127.0.0.1:8000'


def divider(title: str):
    print(f'\n{"=" * 60}\n【{title}】\n{"=" * 60}')


def main():
    client = httpx.Client(timeout=90)

    divider('健康检查 /health')
    print(json.dumps(client.get(f'{BASE}/health').json(), ensure_ascii=False, indent=2))

    divider('创建会话')
    resp = client.post(f'{BASE}/api/v1/chat/session', json={'channel': 'web'})
    resp.raise_for_status()
    data = resp.json()
    session_id = data['session']['session_id']
    print(f'会话ID: {session_id}')
    print(f'欢迎语: {data["welcome_message"]}')
    print(f'快捷回复: {data["quick_replies"]}')

    scenarios = [
        ('订单查询（ReAct: query_order 工具）', '帮我查一下订单 ORDER20260815001 到哪了'),
        ('RAG 政策问答（知识库检索）', '退换货政策是什么'),
        ('取消订单（ReAct: refund 工具）', 'ORDER20260820002 不想要了，帮我取消掉'),
        ('商品咨询（RAG + 语义匹配）', '推荐一款耳机，怎么样'),
        ('投诉（情感分析 + 转人工）', '你们这个东西太差了，我要投诉！'),
        ('问候（LLM 直接回复）', '谢谢，祝生意兴隆'),
    ]

    for title, text in scenarios:
        divider(title)
        print(f'👤 用户: {text}')
        resp = client.post(f'{BASE}/api/v1/chat/send',
                           json={'session_id': session_id, 'content': text})
        resp.raise_for_status()
        data = resp.json()
        intent = data['intent']
        print(f'🏷️  意图: {intent["intent_name"]}({intent["intent_code"]}) '
              f'置信度={intent["confidence"]:.2f} 处理器={intent["handler_type"]}')
        if intent['entities']:
            print(f'🔎 实体: {[(e["type"], e["value"]) for e in intent["entities"]]}')
        print(f'❤️  情感: {data["sentiment"]} ({data["sentiment_score"]:+.2f}) '
              f'策略={data["response_strategy"].get("tone")}')
        if data['tool_trace']:
            for t in data['tool_trace']:
                print(f'🔧 工具: {t["tool"]} 参数={t.get("params", {})}')
        print(f'🤖 小e: {data["response"]}')
        print(f'↩️  快捷回复: {data["quick_replies"]}  转人工={data["need_transfer"]}')

    divider('意图识别独立接口')
    resp = client.post(f'{BASE}/api/v1/intent/recognize', json={'text': '上周买的鞋子什么时候发货'})
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))

    divider('知识库语义检索')
    resp = client.post(f'{BASE}/api/v1/knowledge/search', json={'query': '东西坏了怎么处理', 'top_k': 3})
    data = resp.json()
    for hit in data['hits']:
        print(f"  [{hit['score']:.3f}] ({hit['category']}) {hit['question']}")

    divider('订单 API')
    resp = client.get(f'{BASE}/api/v1/order/ORDER20260820002')
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))

    divider('评价会话')
    resp = client.post(f'{BASE}/api/v1/chat/rate', json={'session_id': session_id, 'score': 5})
    print(resp.json())

    divider('数据看板 /analytics/overview')
    print(json.dumps(client.get(f'{BASE}/api/v1/analytics/overview').json(), ensure_ascii=False, indent=2))

    divider('测试完成')
    print('✅ 全部接口冒烟测试通过')


if __name__ == '__main__':
    try:
        main()
    except httpx.HTTPError as e:
        print(f'❌ 请求失败: {e}')
        if e.response is not None:
            print(e.response.text)
        sys.exit(1)
