# backend/app/services/cache.py
"""内存缓存服务（简化版：代替 Redis）"""
import time
from typing import Any, Optional


class MemoryCache:
    """带 TTL 的内存字典缓存"""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        value, expire_at = item
        if expire_at and time.time() > expire_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self._store[key] = (value, time.time() + ttl if ttl > 0 else None)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# 全局缓存实例
cache = MemoryCache()
