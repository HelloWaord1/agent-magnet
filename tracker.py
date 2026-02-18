"""Silent behavioral tracking — zero visibility in API responses."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field


@dataclass
class _Event:
    ts: float
    endpoint: str
    params: dict
    fingerprint: str


@dataclass
class _AgentProfile:
    fingerprint: str
    first_seen: float
    last_seen: float = 0
    request_count: int = 0
    endpoints_used: dict[str, int] = field(default_factory=dict)
    tools_used: dict[str, int] = field(default_factory=dict)
    user_agents: set[str] = field(default_factory=set)


class AgentTracker:
    """In-memory behavioral tracker. Never exposes data in public API responses."""

    def __init__(self) -> None:
        self._events: list[_Event] = []
        self._agents: dict[str, _AgentProfile] = {}
        self._max_events = 10_000

    # -- fingerprinting ------------------------------------------------------

    @staticmethod
    def fingerprint(
        user_agent: str = "",
        accept: str = "",
        accept_encoding: str = "",
        accept_language: str = "",
        ip: str = "",
    ) -> str:
        raw = f"{user_agent}|{accept}|{accept_encoding}|{accept_language}|{ip}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # -- event logging -------------------------------------------------------

    def log_request(
        self,
        fingerprint: str,
        endpoint: str,
        params: dict | None = None,
        user_agent: str = "",
    ) -> None:
        now = time.time()

        # Record event
        ev = _Event(ts=now, endpoint=endpoint, params=params or {}, fingerprint=fingerprint)
        self._events.append(ev)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        # Update agent profile
        agent = self._agents.get(fingerprint)
        if agent is None:
            agent = _AgentProfile(fingerprint=fingerprint, first_seen=now)
            self._agents[fingerprint] = agent
        agent.last_seen = now
        agent.request_count += 1
        agent.endpoints_used[endpoint] = agent.endpoints_used.get(endpoint, 0) + 1
        if user_agent:
            agent.user_agents.add(user_agent)

    def log_tool_use(self, fingerprint: str, tool_name: str) -> None:
        agent = self._agents.get(fingerprint)
        if agent:
            agent.tools_used[tool_name] = agent.tools_used.get(tool_name, 0) + 1

    # -- internal analytics (only for authenticated endpoints) ---------------

    def summary(self) -> dict:
        now = time.time()
        active_1h = sum(1 for a in self._agents.values() if (now - a.last_seen) < 3600)
        return {
            "total_agents": len(self._agents),
            "active_last_hour": active_1h,
            "total_events": len(self._events),
            "top_endpoints": self._top_endpoints(20),
            "top_agents": self._top_agents(10),
        }

    def recent_events(self, limit: int = 50) -> list[dict]:
        return [
            {
                "ts": e.ts,
                "endpoint": e.endpoint,
                "params": e.params,
                "fingerprint": e.fingerprint,
            }
            for e in reversed(self._events[-limit:])
        ]

    def agent_journey(self, fingerprint: str) -> dict | None:
        agent = self._agents.get(fingerprint)
        if agent is None:
            return None
        events = [
            {"ts": e.ts, "endpoint": e.endpoint, "params": e.params}
            for e in self._events
            if e.fingerprint == fingerprint
        ]
        return {
            "fingerprint": agent.fingerprint,
            "first_seen": agent.first_seen,
            "last_seen": agent.last_seen,
            "request_count": agent.request_count,
            "endpoints_used": agent.endpoints_used,
            "tools_used": agent.tools_used,
            "user_agents": list(agent.user_agents),
            "events": events[-200:],
        }

    # -- private helpers -----------------------------------------------------

    def _top_endpoints(self, limit: int) -> list[dict]:
        counter: dict[str, int] = {}
        for e in self._events:
            counter[e.endpoint] = counter.get(e.endpoint, 0) + 1
        return [
            {"endpoint": k, "count": v}
            for k, v in sorted(counter.items(), key=lambda x: x[1], reverse=True)[:limit]
        ]

    def _top_agents(self, limit: int) -> list[dict]:
        agents = sorted(self._agents.values(), key=lambda a: a.request_count, reverse=True)
        return [
            {
                "fingerprint": a.fingerprint,
                "request_count": a.request_count,
                "first_seen": a.first_seen,
                "last_seen": a.last_seen,
                "endpoints": len(a.endpoints_used),
            }
            for a in agents[:limit]
        ]
