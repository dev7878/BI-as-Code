"""Query-result cache. Prototype: in-process SimpleCache. Production: Redis (same interface).

Set RBC_BI_CACHE=redis and RBC_BI_REDIS_URL to switch; nothing else changes.
"""

from __future__ import annotations

import os

from flask_caching import Cache

# Seconds a dataset query result stays cached, by the dataset's `refresh`.
# NB: Flask-Caching treats a timeout of 0 as "never expire", so realtime uses 1 second: effectively
# uncached, while still sharing one query between the components of a single page load.
TTL = {"realtime": 1, "hourly": 3600, "daily": 86400}


def ttl_seconds(refresh: str) -> int:
    return TTL[refresh]


def make_cache() -> Cache:
    if os.environ.get("RBC_BI_CACHE") == "redis":
        return Cache(config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": os.environ["RBC_BI_REDIS_URL"]})
    return Cache(config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 3600})
