"""Cross-source crypto analytics — unique metrics not available from any single API."""

from __future__ import annotations

from data_sources import DataSources


class CryptoAnalytics:
    """Combines CoinGecko + DeFiLlama + Fear&Greed into unique cross-source metrics."""

    def __init__(self, ds: DataSources) -> None:
        self._ds = ds

    # -- public analysis methods ---------------------------------------------

    async def market_overview(self) -> dict:
        global_data, fng, protocols, chains = await _gather(
            self._ds.get_global_market(),
            self._ds.get_fear_greed(),
            self._ds.get_protocols(),
            self._ds.get_chain_tvls(),
        )

        gd = global_data.get("data", {})
        total_mcap = gd.get("total_market_cap", {}).get("usd", 0)
        total_vol = gd.get("total_volume", {}).get("usd", 0)
        mcap_change_24h = gd.get("market_cap_change_percentage_24h_usd", 0)
        btc_dom = gd.get("market_cap_percentage", {}).get("btc", 0)
        eth_dom = gd.get("market_cap_percentage", {}).get("eth", 0)
        active_coins = gd.get("active_cryptocurrencies", 0)

        total_tvl = sum(c.get("tvl", 0) for c in chains) if chains else 0

        # Unique: mcap-to-TVL ratio
        mcap_tvl_ratio = round(total_mcap / total_tvl, 2) if total_tvl else None

        # Unique: sentiment divergence
        sentiment_div = _sentiment_divergence(fng.get("value", 50), mcap_change_24h)

        return {
            "total_market_cap_usd": total_mcap,
            "total_volume_24h_usd": total_vol,
            "market_cap_change_24h_pct": round(mcap_change_24h, 2),
            "btc_dominance": round(btc_dom, 2),
            "eth_dominance": round(eth_dom, 2),
            "active_cryptocurrencies": active_coins,
            "total_defi_tvl_usd": round(total_tvl, 0),
            "mcap_to_tvl_ratio": mcap_tvl_ratio,
            "fear_greed": fng,
            "sentiment_divergence": sentiment_div,
        }

    async def token_analysis(self, coin_id: str) -> dict:
        coin, fng = await _gather(
            self._ds.get_coin_detail(coin_id),
            self._ds.get_fear_greed(),
        )

        md = coin.get("market_data", {})
        price = md.get("current_price", {}).get("usd")
        mcap = md.get("market_cap", {}).get("usd", 0)
        vol24 = md.get("total_volume", {}).get("usd", 0)
        change_24h = md.get("price_change_percentage_24h", 0)
        change_7d = md.get("price_change_percentage_7d", 0)
        change_30d = md.get("price_change_percentage_30d", 0)
        ath = md.get("ath", {}).get("usd")
        ath_change = md.get("ath_change_percentage", {}).get("usd")
        circulating = md.get("circulating_supply")
        total_supply = md.get("total_supply")

        # Unique: volume/mcap ratio (liquidity indicator)
        vol_mcap_ratio = round(vol24 / mcap, 4) if mcap else None

        # Unique: sentiment divergence
        sentiment_div = _sentiment_divergence(fng.get("value", 50), change_24h or 0)

        # Try to find DeFi TVL
        defi_tvl = None
        try:
            protocols = await self._ds.get_protocols()
            slug = coin.get("id", "").lower()
            name_lower = coin.get("name", "").lower()
            symbol_lower = coin.get("symbol", "").lower()
            for p in protocols:
                p_slug = p.get("slug", "").lower()
                p_name = p.get("name", "").lower()
                p_symbol = p.get("symbol", "").lower()
                if p_slug == slug or p_name == name_lower or p_symbol == symbol_lower:
                    defi_tvl = p.get("tvl")
                    break
        except Exception:
            pass

        return {
            "coin_id": coin_id,
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
            "price_usd": price,
            "market_cap_usd": mcap,
            "volume_24h_usd": vol24,
            "volume_mcap_ratio": vol_mcap_ratio,
            "price_change_24h_pct": round(change_24h or 0, 2),
            "price_change_7d_pct": round(change_7d or 0, 2),
            "price_change_30d_pct": round(change_30d or 0, 2),
            "ath_usd": ath,
            "ath_change_pct": round(ath_change, 2) if ath_change else None,
            "circulating_supply": circulating,
            "total_supply": total_supply,
            "defi_tvl_usd": defi_tvl,
            "fear_greed": fng,
            "sentiment_divergence": sentiment_div,
        }

    async def trending_with_context(self) -> dict:
        trending, fng, global_data = await _gather(
            self._ds.get_trending(),
            self._ds.get_fear_greed(),
            self._ds.get_global_market(),
        )

        gd = global_data.get("data", {})
        mcap_change = gd.get("market_cap_change_percentage_24h_usd", 0)

        coins = []
        for item in trending.get("coins", [])[:15]:
            c = item.get("item", {})
            coins.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "symbol": c.get("symbol"),
                "market_cap_rank": c.get("market_cap_rank"),
                "price_btc": c.get("price_btc"),
                "score": c.get("score"),
            })

        return {
            "trending_coins": coins,
            "market_direction": "bullish" if mcap_change > 1 else "bearish" if mcap_change < -1 else "neutral",
            "market_cap_change_24h_pct": round(mcap_change, 2),
            "fear_greed": fng,
        }

    async def protocol_comparison(self, slugs: list[str]) -> dict:
        # Get protocols list for change data
        try:
            all_protocols = await self._ds.get_protocols()
            proto_by_slug = {p.get("slug", "").lower(): p for p in all_protocols}
        except Exception:
            proto_by_slug = {}

        results = []
        for slug in slugs[:10]:
            try:
                p = await self._ds.get_protocol_detail(slug)
                # currentChainTvls has per-chain current TVL; sum for total
                current_tvls = p.get("currentChainTvls", {})
                total_tvl = sum(
                    v for k, v in current_tvls.items()
                    if isinstance(v, (int, float))
                    and "borrowed" not in k.lower()
                    and "staking" not in k.lower()
                    and "pool2" not in k.lower()
                    and "vesting" not in k.lower()
                )
                # Get change data from protocols list
                list_entry = proto_by_slug.get(slug.lower(), {})
                results.append({
                    "slug": slug,
                    "name": p.get("name"),
                    "symbol": p.get("symbol"),
                    "tvl_usd": round(total_tvl, 2),
                    "chain": p.get("chain"),
                    "chains": p.get("chains", []),
                    "category": p.get("category"),
                    "change_1h": list_entry.get("change_1h"),
                    "change_1d": list_entry.get("change_1d"),
                    "change_7d": list_entry.get("change_7d"),
                    "mcap": p.get("mcap"),
                    "url": p.get("url"),
                })
            except Exception:
                results.append({"slug": slug, "error": "not found"})

        return {"protocols": results, "count": len(results)}

    async def chain_tvl_ranking(self) -> dict:
        chains = await self._ds.get_chain_tvls()

        ranked = sorted(chains, key=lambda c: c.get("tvl", 0), reverse=True)
        top = []
        for c in ranked[:20]:
            top.append({
                "name": c.get("name"),
                "tvl": c.get("tvl"),
                "tokenSymbol": c.get("tokenSymbol"),
                "gecko_id": c.get("gecko_id"),
            })

        return {"chains": top, "total_tvl": sum(c.get("tvl", 0) for c in chains)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402


async def _gather(*coros):
    return await asyncio.gather(*coros)


def _sentiment_divergence(fng_value: int, price_change_pct: float) -> dict:
    """Detect when sentiment and price action diverge.

    fng_value: 0-100 (0=extreme fear, 100=extreme greed)
    price_change_pct: 24h price change percentage
    """
    # Normalize FNG to -1..+1 scale (50 = neutral)
    fng_norm = (fng_value - 50) / 50

    # Normalize price change (clamp to -10..+10 range, then to -1..+1)
    price_norm = max(-1, min(1, price_change_pct / 10))

    # Divergence: sentiment says one thing, price does another
    divergence = round(fng_norm - price_norm, 3)

    if divergence > 0.4:
        signal = "greedy_despite_drop"
        desc = "Market sentiment is greedy while prices are falling — potential complacency"
    elif divergence < -0.4:
        signal = "fearful_despite_rise"
        desc = "Market sentiment is fearful while prices are rising — potential opportunity"
    else:
        signal = "aligned"
        desc = "Sentiment and price action are broadly aligned"

    return {
        "signal": signal,
        "divergence_score": divergence,
        "description": desc,
        "fear_greed_normalized": round(fng_norm, 3),
        "price_action_normalized": round(price_norm, 3),
    }
