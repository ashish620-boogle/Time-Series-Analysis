import json
from typing import Any, Optional

import redis.asyncio as redis


class Store:
    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url
        self._redis = None
        self._memory = {}

    async def connect(self) -> None:
        if not self._redis_url:
            return
        try:
            client = redis.from_url(self._redis_url, decode_responses=True)
            await client.ping()
        except Exception:
            self._redis = None
            return
        self._redis = client

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def get_json(self, key: str, default: Optional[Any] = None) -> Any:
        if self._redis is not None:
            raw = await self._redis.get(key)
            if raw is None:
                return default
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return default
        return self._memory.get(key, default)

    async def set_json(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        if self._redis is not None:
            payload = json.dumps(value)
            await self._redis.set(key, payload, ex=ex)
        else:
            self._memory[key] = value
