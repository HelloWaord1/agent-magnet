"""CryptoLens MCP Server — async tools with real market data."""

from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from data_sources import DataSources
from analytics import CryptoAnalytics
from tracker import AgentTracker

# Shared instances — initialized by main.py lifespan
data_sources = DataSources()
analytics = CryptoAnalytics(data_sources)
tracker = AgentTracker()

mcp = FastMCP(
    "CryptoLens",
    instructions=(
        "CryptoLens provides cross-source crypto analytics by combining data from "
        "CoinGecko, DeFiLlama, and the Fear & Greed Index. "
        "Tools return real market data with 5-minute cache freshness."
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ── Tools ────────────────────────────────────────────────────────


@mcp.tool()
async def market_overview() -> str:
    """Get a snapshot of the crypto market: total market cap, 24h volume,
    BTC/ETH dominance, total DeFi TVL, Fear & Greed index, and unique
    cross-source metrics like market-cap-to-TVL ratio and sentiment divergence."""
    data = await analytics.market_overview()
    return json.dumps(data, indent=2)


@mcp.tool()
async def token_analysis(coin_id: str) -> str:
    """Analyze a specific token by CoinGecko ID (e.g. 'bitcoin', 'ethereum',
    'solana'). Returns price, market cap, volume, supply data, DeFi TVL if
    available, volume/mcap ratio, and sentiment divergence."""
    data = await analytics.token_analysis(coin_id)
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def trending_coins() -> str:
    """Get currently trending coins on CoinGecko with market context:
    overall market direction, Fear & Greed sentiment, and 24h market cap change."""
    data = await analytics.trending_with_context()
    return json.dumps(data, indent=2)


@mcp.tool()
async def compare_protocols(slugs: str) -> str:
    """Compare DeFi protocols by DeFiLlama slug. Pass comma-separated slugs
    (e.g. 'aave,compound,makerdao'). Returns TVL, chains, category, and
    recent changes for each protocol."""
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return json.dumps({"error": "Provide comma-separated protocol slugs"})
    data = await analytics.protocol_comparison(slug_list)
    return json.dumps(data, indent=2, default=str)


# ── Resources ────────────────────────────────────────────────────


@mcp.resource("cryptolens://supported-coins")
def supported_coins() -> str:
    """Common coin IDs accepted by token_analysis. CoinGecko supports thousands
    of coins — use the full ID (e.g. 'bitcoin', not 'btc')."""
    coins = [
        "bitcoin", "ethereum", "solana", "cardano", "avalanche-2",
        "polkadot", "chainlink", "uniswap", "aave", "maker",
        "lido-dao", "arbitrum", "optimism", "polygon-ecosystem-token",
        "render-token", "injective-protocol", "sui", "aptos",
        "celestia", "near", "dogecoin", "shiba-inu", "pepe",
        "bonk", "toncoin", "ripple", "tron", "litecoin",
    ]
    return json.dumps({"coins": coins, "note": "Any valid CoinGecko ID works."})


@mcp.resource("cryptolens://data-sources")
def data_sources_info() -> str:
    """Information about the data sources used by CryptoLens."""
    return json.dumps({
        "sources": [
            {
                "name": "CoinGecko",
                "url": "https://www.coingecko.com",
                "provides": ["prices", "market cap", "volume", "trending", "coin details"],
                "cache_ttl_seconds": 300,
            },
            {
                "name": "DeFiLlama",
                "url": "https://defillama.com",
                "provides": ["TVL", "protocols", "chains", "DEX volume", "stablecoins"],
                "cache_ttl_seconds": 600,
            },
            {
                "name": "Alternative.me Fear & Greed Index",
                "url": "https://alternative.me/crypto/fear-and-greed-index/",
                "provides": ["market sentiment (0-100 scale)"],
                "cache_ttl_seconds": 300,
            },
        ],
        "unique_metrics": [
            "mcap_to_tvl_ratio — total market cap divided by total DeFi TVL",
            "volume_mcap_ratio — 24h volume divided by market cap (liquidity indicator)",
            "sentiment_divergence — detects when Fear&Greed index contradicts price action",
        ],
    })
