"""Lightweight MCP HTTP client. No SDK dependency, Python 3.10+ compatible.

Uses JSON-RPC over HTTP POST to communicate with any MCP server.
Does NOT depend on anyio/task groups (which break in Python 3.10).

Supports:
- streamable_http / http transport (POST JSON-RPC)
- Tool discovery (tools/list)
- Tool execution (tools/call)

For stdio transport, use tools/mcp_loader.py (MCP SDK).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """Connects to an MCP server via HTTP, discovers and calls tools.

    Usage:
        client = MCPClient("http://localhost:8001/mcp")
        client.connect()
        tools = client.list_tools()
        result = client.call_tool("mcp_question", {"question": "..."})
        client.close()
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ):
        self.url = url
        self.headers = headers or {}
        self._http = httpx.Client(timeout=timeout, trust_env=False)
        self._request_id = 0
        self._tools: list[dict] = []

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request, return the result field."""
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_id(),
        }
        if params:
            payload["params"] = params

        resp = self._http.post(
            self.url,
            json=payload,
            headers={"Content-Type": "application/json", **self.headers},
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            err = data["error"]
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
        return data.get("result", {})

    def connect(self) -> None:
        """Initialize MCP session and discover tools."""
        # 1. Initialize handshake
        self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mini-agent", "version": "0.1.0"},
        })
        # Send initialized notification (no response expected)
        try:
            self._http.post(
                self.url,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers={"Content-Type": "application/json", **self.headers},
            )
        except Exception:
            pass  # notification, no response needed

        logger.info(f"MCP initialized: {self.url}")

        # 2. Discover tools
        result = self._send("tools/list")
        self._tools = result.get("tools", [])
        logger.info(f"MCP discovered {len(self._tools)} tools from {self.url}")
        for t in self._tools:
            logger.debug(f"  - {t.get('name')}: {(t.get('description') or '')[:60]}")

    def list_tools(self) -> list[dict]:
        """Return discovered tool schemas (name, description, inputSchema)."""
        return self._tools

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        """Call a tool by name, return concatenated text content.

        Args:
            name: Tool name (e.g. "mcp_question")
            arguments: Tool arguments dict

        Returns:
            Text content from the tool result
        """
        result = self._send("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        # MCP result has "content" which is a list of content items
        contents = result.get("content", [])
        texts = []
        for c in contents:
            if isinstance(c, dict) and c.get("type") == "text":
                texts.append(c.get("text", ""))
            elif isinstance(c, dict):
                texts.append(str(c))
            else:
                texts.append(str(c))
        return "\n".join(texts)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


__all__ = ["MCPClient"]
