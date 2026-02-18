"""Async data fetchers with TTL cache for CoinGecko, DeFiLlama, Fear&Greed."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    data: Any
    ts: float
    ttl: float

    @property
    def fresh(self) -> bool:
        return (time.time() - self.ts) < self.ttl

    @property
    def age_seconds(self) -> float:
        return round(time.time() - self.ts, 1)


# ---------------------------------------------------------------------------
# DataSources
# ---------------------------------------------------------------------------

_COINGECKO = "https://api.coingecko.com/api/v3"
_DEFILLAMA = "https://api.llama.fi"
_FEAR_GREED = "https://api.alternative.me/fng/"

_SHORT_TTL = 300.0   # 5 min — prices, market
_LONG_TTL = 600.0    # 10 min — protocols, trending, chains

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CryptoLens/2.0",
}


class DataSources:
    """Thin async wrappers around free crypto APIs with stale-while-revalidate."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, _CacheEntry] = {}

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers=_HEADERS,
            follow_redirects=True,
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- internal helpers ----------------------------------------------------

    async def _get(self, url: str, params: dict | None = None) -> Any:
        assert self._client is not None, "call start() first"
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    async def _cached(self, key: str, ttl: float, fetcher) -> Any:
        entry = self._cache.get(key)
        if entry and entry.fresh:
            return entry.data
        try:
            data = await fetcher()
            self._cache[key] = _CacheEntry(data=data, ts=time.time(), ttl=ttl)
            return data
        except Exception:
            # stale-while-revalidate
            if entry is not None:
                return entry.data
            raise

    def cache_stats(self) -> dict:
        now = time.time()
        total = len(self._cache)
        fresh = sum(1 for e in self._cache.values() if e.fresh)
        return {"total_keys": total, "fresh": fresh, "stale": total - fresh}

    # -- CoinGecko -----------------------------------------------------------

    async def get_prices(
        self,
        ids: str = "bitcoin,ethereum,solana,cardano,avalanche-2",
    ) -> dict:
        async def fetch():
            return await self._get(
                f"{_COINGECKO}/simple/price",
                params={
                    "ids": ids,
                    "vs_currencies": "usd",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                    "include_24hr_change": "true",
                },
            )
        return await self._cached(f"prices:{ids}", _SHORT_TTL, fetch)

    async def get_trending(self) -> dict:
        async def fetch():
            return await self._get(f"{_COINGECKO}/search/trending")
        return await self._cached("trending", _LONG_TTL, fetch)

    async def get_global_market(self) -> dict:
        async def fetch():
            return await self._get(f"{_COINGECKO}/global")
        return await self._cached("global", _SHORT_TTL, fetch)

    async def get_coin_detail(self, coin_id: str) -> dict:
        async def fetch():
            return await self._get(
                f"{_COINGECKO}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
        return await self._cached(f"coin:{coin_id}", _SHORT_TTL, fetch)

    # -- DeFiLlama -----------------------------------------------------------

    async def get_protocols(self) -> list[dict]:
        async def fetch():
            return await self._get(f"{_DEFILLAMA}/protocols")
        return await self._cached("protocols", _LONG_TTL, fetch)

    async def get_chain_tvls(self) -> list[dict]:
        async def fetch():
            return await self._get(f"{_DEFILLAMA}/v2/chains")
        return await self._cached("chains", _LONG_TTL, fetch)

    async def get_protocol_detail(self, slug: str) -> dict:
        async def fetch():
            return await self._get(f"{_DEFILLAMA}/protocol/{slug}")
        return await self._cached(f"protocol:{slug}", _LONG_TTL, fetch)

    async def get_dex_overview(self) -> dict:
        async def fetch():
            return await self._get(f"{_DEFILLAMA}/overview/dexs")
        return await self._cached("dex_overview", _LONG_TTL, fetch)

    async def get_stablecoins(self) -> dict:
        async def fetch():
            return await self._get(f"{_DEFILLAMA}/stablecoins")
        return await self._cached("stablecoins", _LONG_TTL, fetch)

    # -- Fear & Greed --------------------------------------------------------

    async def get_fear_greed(self) -> dict:
        async def fetch():
            raw = await self._get(_FEAR_GREED, params={"limit": "1"})
            entry = raw.get("data", [{}])[0]
            return {
                "value": int(entry.get("value", 0)),
                "label": entry.get("value_classification", "unknown"),
                "timestamp": entry.get("timestamp"),
            }
        return await self._cached("fng", _SHORT_TTL, fetch)
