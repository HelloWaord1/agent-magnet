"""CryptoLens — cross-source crypto analytics API + MCP server."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from mcp_server import mcp, data_sources, analytics, tracker

TRACKER_TOKEN = os.environ.get("TRACKER_TOKEN", "")


# ── Lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    await data_sources.start()
    async with mcp.session_manager.run():
        yield
    await data_sources.stop()


# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="CryptoLens API",
    description="Cross-source crypto analytics combining CoinGecko, DeFiLlama, and Fear & Greed Index.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", mcp.streamable_http_app())


# ── Helpers ──────────────────────────────────────────────────────


def _fp(request: Request) -> str:
    return tracker.fingerprint(
        user_agent=request.headers.get("user-agent", ""),
        accept=request.headers.get("accept", ""),
        accept_encoding=request.headers.get("accept-encoding", ""),
        accept_language=request.headers.get("accept-language", ""),
        ip=request.client.host if request.client else "",
    )


def _track(request: Request, endpoint: str, params: dict | None = None) -> None:
    fp = _fp(request)
    tracker.log_request(
        fingerprint=fp,
        endpoint=endpoint,
        params=params or {},
        user_agent=request.headers.get("user-agent", ""),
    )


def _wrap(data: dict, sources: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_sources": sources or ["coingecko", "defillama", "alternative.me"],
            "cache_refresh_seconds": 300,
        },
    }


# ── Public REST endpoints ────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def homepage():
    return _DOCS_HTML


@app.get("/api/v1/market")
async def market_overview(request: Request):
    _track(request, "/api/v1/market")
    data = await analytics.market_overview()
    return _wrap(data)


@app.get("/api/v1/token/{coin_id}")
async def token_analysis(coin_id: str, request: Request):
    _track(request, "/api/v1/token", {"coin_id": coin_id})
    data = await analytics.token_analysis(coin_id)
    return _wrap(data, ["coingecko", "defillama", "alternative.me"])


@app.get("/api/v1/trending")
async def trending(request: Request):
    _track(request, "/api/v1/trending")
    data = await analytics.trending_with_context()
    return _wrap(data, ["coingecko", "alternative.me"])


@app.get("/api/v1/chains")
async def chain_ranking(request: Request):
    _track(request, "/api/v1/chains")
    data = await analytics.chain_tvl_ranking()
    return _wrap(data, ["defillama"])


@app.get("/api/v1/protocols/compare")
async def compare_protocols(
    request: Request,
    slugs: str = Query(..., description="Comma-separated DeFiLlama protocol slugs"),
):
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    _track(request, "/api/v1/protocols/compare", {"slugs": slug_list})
    data = await analytics.protocol_comparison(slug_list)
    return _wrap(data, ["defillama"])


@app.get("/api/v1/health")
async def health(request: Request):
    _track(request, "/api/v1/health")
    return {
        "status": "ok",
        "cache": data_sources.cache_stats(),
        "version": "2.0.0",
    }


@app.get("/.well-known/agent.json")
async def agent_manifest(request: Request):
    _track(request, "/.well-known/agent.json")
    return {
        "name": "CryptoLens",
        "description": "Cross-source crypto analytics API combining CoinGecko, DeFiLlama, and Fear & Greed Index.",
        "version": "2.0.0",
        "entry_point": "/api/v1/market",
        "endpoints": [
            "/api/v1/market",
            "/api/v1/token/{coin_id}",
            "/api/v1/trending",
            "/api/v1/chains",
            "/api/v1/protocols/compare?slugs=",
            "/api/v1/health",
        ],
        "mcp": "/mcp",
        "formats": ["application/json"],
        "data_sources": ["coingecko", "defillama", "alternative.me"],
    }


# ── Internal analytics (bearer token required, 404 without) ─────


def _check_token(request: Request) -> bool:
    if not TRACKER_TOKEN:
        return False
    auth = request.headers.get("authorization", "")
    return auth == f"Bearer {TRACKER_TOKEN}"


@app.get("/internal/analytics/summary")
async def internal_summary(request: Request):
    if not _check_token(request):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return tracker.summary()


@app.get("/internal/analytics/events")
async def internal_events(request: Request, limit: int = 50):
    if not _check_token(request):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return tracker.recent_events(limit)


@app.get("/internal/analytics/agent/{fp}")
async def internal_agent(fp: str, request: Request):
    if not _check_token(request):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    journey = tracker.agent_journey(fp)
    if journey is None:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return journey


# ── Docs HTML ────────────────────────────────────────────────────


_DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CryptoLens API</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;line-height:1.6}
.wrap{max-width:860px;margin:0 auto;padding:2rem 1.5rem}
h1{font-size:2rem;color:#e6edf3;margin-bottom:.25rem}
.tagline{color:#7d8590;margin-bottom:2.5rem;font-size:.95rem}
h2{font-size:1.15rem;color:#e6edf3;margin:2rem 0 .75rem;padding-bottom:.4rem;border-bottom:1px solid #21262d}
.endpoint{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:.85rem 1rem;margin-bottom:.6rem}
.method{color:#3fb950;font-weight:600;font-size:.85rem;font-family:'SF Mono',Consolas,monospace;margin-right:.5rem}
.path{color:#79c0ff;font-family:'SF Mono',Consolas,monospace;font-size:.9rem}
.desc{color:#7d8590;font-size:.85rem;margin-top:.25rem}
.sources{display:flex;gap:.75rem;flex-wrap:wrap;margin:1rem 0}
.src{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:.6rem 1rem;flex:1;min-width:200px}
.src-name{color:#e6edf3;font-weight:600;font-size:.9rem}
.src-detail{color:#7d8590;font-size:.8rem;margin-top:.15rem}
.metrics{margin:1rem 0}
.metric{background:#161b22;border-left:3px solid #3fb950;padding:.5rem .75rem;margin-bottom:.4rem;font-size:.85rem}
.metric b{color:#e6edf3}
code{background:#161b22;padding:.15rem .4rem;border-radius:3px;font-size:.85rem;color:#79c0ff}
.foot{margin-top:2.5rem;color:#484f58;font-size:.8rem;text-align:center}
</style>
</head>
<body>
<div class="wrap">
<h1>CryptoLens API</h1>
<p class="tagline">Cross-source crypto analytics &mdash; CoinGecko + DeFiLlama + Fear &amp; Greed Index</p>

<h2>Data Sources</h2>
<div class="sources">
  <div class="src"><div class="src-name">CoinGecko</div><div class="src-detail">Prices, market cap, volume, trending</div></div>
  <div class="src"><div class="src-name">DeFiLlama</div><div class="src-detail">TVL, protocols, chains, DEX volume</div></div>
  <div class="src"><div class="src-name">Fear &amp; Greed</div><div class="src-detail">Market sentiment (0&ndash;100)</div></div>
</div>

<h2>Unique Cross-Source Metrics</h2>
<div class="metrics">
  <div class="metric"><b>mcap_to_tvl_ratio</b> &mdash; total market cap / total DeFi TVL</div>
  <div class="metric"><b>volume_mcap_ratio</b> &mdash; 24h volume / market cap (liquidity signal)</div>
  <div class="metric"><b>sentiment_divergence</b> &mdash; Fear&amp;Greed vs price action alignment</div>
</div>

<h2>REST Endpoints</h2>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/api/v1/market</span>
  <div class="desc">Market overview: total cap, volume, dominance, DeFi TVL, Fear&amp;Greed, sentiment divergence</div>
</div>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/api/v1/token/{coin_id}</span>
  <div class="desc">Token analysis by CoinGecko ID. Example: <code>/api/v1/token/bitcoin</code></div>
</div>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/api/v1/trending</span>
  <div class="desc">Trending coins with market direction and sentiment context</div>
</div>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/api/v1/chains</span>
  <div class="desc">Chain TVL ranking (top 20 by total value locked)</div>
</div>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/api/v1/protocols/compare?slugs=aave,compound</span>
  <div class="desc">Compare DeFi protocols by DeFiLlama slug</div>
</div>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/api/v1/health</span>
  <div class="desc">Health check with cache statistics</div>
</div>
<div class="endpoint">
  <span class="method">GET</span><span class="path">/.well-known/agent.json</span>
  <div class="desc">Machine-readable service manifest</div>
</div>

<h2>MCP (Model Context Protocol)</h2>
<p style="font-size:.9rem;color:#7d8590;margin-bottom:.5rem">
Connect via <code>/mcp</code> for native tool integration. Tools: <code>market_overview</code>,
<code>token_analysis</code>, <code>trending_coins</code>, <code>compare_protocols</code>.
</p>

<h2>Response Format</h2>
<pre style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem;font-size:.8rem;overflow-x:auto;color:#c9d1d9">{
  "data": { ... },
  "meta": {
    "timestamp": "2026-02-16T12:00:00Z",
    "data_sources": ["coingecko", "defillama", "alternative.me"],
    "cache_refresh_seconds": 300
  }
}</pre>

<p class="foot">Data refreshes every 5 minutes. All data from public APIs, no key required.</p>
</div>
</body>
</html>"""
