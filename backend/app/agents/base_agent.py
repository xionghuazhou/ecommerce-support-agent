# backend/app/agents/base_agent.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from datetime import datetime
import uuid

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class BaseAgent(ABC):
    """Agent 基类

    提供 Agent 的基础能力：
    - 会话管理
    - 工具注册
    - 状态追踪
    - 历史记录
    """

    def __init__(self, session_id: str, user_id: Optional[int] = None):
        self.session_id = session_id
        self.user_id = user_id
        self.agent_id = str(uuid.uuid4())
        self.state: Dict[str, Any] = {}
        self.tools: Dict[str, Any] = {}
        self.conversation_history: List[Dict[str, str]] = []
        self.created_at = self._get_timestamp()

        logger.info(f'Agent {self.agent_id} 初始化，会话: {session_id}')

    def register_tool(self, name: str, tool: Any) -> None:
        """注册工具"""
        self.tools[name] = tool
        logger.debug(f'工具注册: {name}')

    def get_tool(self, name: str) -> Optional[Any]:
        """获取工具"""
        return self.tools.get(name)

    def update_state(self, key: str, value: Any) -> None:
        """更新 Agent 状态"""
        self.state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """读取 Agent 状态"""
        return self.state.get(key, default)

    def add_history(self, role: str, content: str) -> None:
        """追加对话历史"""
        self.conversation_history.append({'role': role, 'content': content})
        # 只保留最近 20 条，避免上下文过长
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

    @staticmethod
    def _get_timestamp() -> str:
        return datetime.now().isoformat()

    @abstractmethod
    async def process_message(self, content: str) -> Dict[str, Any]:
        """处理用户消息，子类必须实现"""
        raise NotImplementedError
