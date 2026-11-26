# backend/app/agents/tools/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """Agent 工具基类"""

    name: str = 'base_tool'
    description: str = ''
    parameters: Dict[str, Any] = {}
    requires_auth: bool = False

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具，返回 {'success': bool, 'response': str, 'data': dict}"""
        raise NotImplementedError
