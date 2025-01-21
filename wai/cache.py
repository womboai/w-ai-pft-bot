import time
from typing import Dict, Optional, Tuple, TypeVar, Generic

T = TypeVar("T")

class TTLCache(Generic[T]):
    def __init__(self, expiration_time=600):  # Default expiration time is 600 seconds (10 minutes)
        self.cache: Dict[str, Tuple[T, float]] = {}
        self.expiration_time = expiration_time

    def set(self, key: str, value: T):
        self.cache[key] = (value, time.time() + self.expiration_time)

    def get(self, key: str) -> Optional[T]:
        if key in self.cache:
            value, expiration = self.cache[key]
            if time.time() < expiration:
                return value
            else:
                self.cache.pop(key)
        return None

    def delete(self, key: str):
        self.cache.pop(key)

    def clear(self):
        self.cache.clear()
    
    def evict(self):
        current_time = time.time()
        expired_keys = [key for key, (_, expiration) in self.cache.items() if current_time >= expiration]
        for key in expired_keys:
            self.cache.pop(key)

    def __repr__(self):
        return f"ExpiringCache({self.cache})"
