"""SQLBot HTTP client — single file, process-shared.

5 endpoints + chart download + response helpers.
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


# ---------- Errors ----------
class SqlBotError(Exception):
    """Base error."""


class SqlBotAuthError(SqlBotError):
    """Token invalid."""


class SqlBotTransientError(SqlBotError):
    """Network/timeout — retryable."""


# ---------- Config ----------
# Default credentials match SQLBot's documented Docker defaults, convenient
# for local development. Production deployments MUST override via env vars
# or sqlbot.yaml - otherwise the client silently authenticates as admin.
_DEFAULT_USERNAME = "admin"
_DEFAULT_PASSWORD = "SQLBot@123456"


@dataclass
class SqlBotConfig:
    """SQLBot connection settings."""

    api_base: str = "http://localhost:18000"
    image_base: str = "http://localhost:18001"
    username: str = _DEFAULT_USERNAME
    password: str = _DEFAULT_PASSWORD
    workspace_id: str = "1"  # MUST be str (SQLBot schema)
    default_datasource_id: int | None = None
    request_timeout: float = 60.0
    auto_retry: int = 1

    @property
    def uses_default_credentials(self) -> bool:
        """True if username or password were left at SQLBot's Docker defaults."""
        return self.username == _DEFAULT_USERNAME or self.password == _DEFAULT_PASSWORD


# ---------- Client ----------
class SqlBotClient:
    """Sync HTTP client. Process-shared (httpx connection pool)."""

    def __init__(self, cfg: SqlBotConfig):
        self.cfg = cfg
        # trust_env=False: skip HTTP_PROXY env vars (avoids host proxy interception)
        self._http = httpx.Client(timeout=cfg.request_timeout, trust_env=False)
        if cfg.uses_default_credentials:
            logger.warning(
                "SqlBotClient using default credentials (admin/SQLBot@123456). "
                "Set SQLBOT_USERNAME/SQLBOT_PASSWORD or sqlbot.yaml for production."
            )

    def close(self) -> None:
        self._http.close()

    def __enter__(self): return self
    def __exit__(self, *_: object): self.close()

    # ----- Internal request with retry -----
    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        token_in: str = "body",
        json_body: dict | None = None,
        params: dict | None = None,
        _retry: int = 0,
    ) -> dict:
        url = f"{self.cfg.api_base.rstrip('/')}{path}"
        body = dict(json_body or {})
        qs = dict(params or {})
        if token:
            if token_in == "query":
                qs["token"] = token
            else:
                body["token"] = token

        try:
            resp = self._http.request(method, url, json=body or None, params=qs or None)
        except httpx.TimeoutException as e:
            raise SqlBotTransientError(f"timeout: {e}") from e
        except httpx.HTTPError as e:
            if _retry < self.cfg.auto_retry:
                return self._request(method, path, token=token, token_in=token_in,
                                    json_body=json_body, params=params, _retry=_retry + 1)
            raise SqlBotTransientError(f"network error: {e}") from e

        # 401/403: re-auth once. Never re-auth the login request itself (that would
        # recurse into login() forever on bad credentials), and advance _retry so a
        # persistent 401 after re-auth raises SqlBotAuthError instead of looping.
        if resp.status_code in (401, 403) and self.cfg.auto_retry > 0 and _retry == 0:
            if path.endswith("/mcp/access_token"):
                raise SqlBotAuthError(f"auth failed {resp.status_code}: {resp.text[:200]}")
            new_token = self.login()
            return self._request(method, path, token=new_token, token_in=token_in,
                                json_body=json_body, params=params, _retry=_retry + 1)

        # 5xx: retry once OR treat as business error
        if resp.status_code >= 500:
            business = self._try_parse_business_error(resp)
            if business is not None:
                return business
            if _retry < self.cfg.auto_retry:
                return self._request(method, path, token=token, token_in=token_in,
                                    json_body=json_body, params=params, _retry=_retry + 1)
            raise SqlBotTransientError(f"server {resp.status_code}: {resp.text[:200]}")

        if resp.status_code in (401, 403):
            raise SqlBotAuthError(f"auth failed {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise SqlBotError(f"client {resp.status_code}: {resp.text[:200]}")

        try:
            payload = resp.json()
        except Exception as e:
            raise SqlBotError(f"non-JSON response: {resp.text[:200]}") from e
        if isinstance(payload, dict) and "code" in payload:
            if payload.get("code") != 0:
                raise SqlBotError(f"code={payload.get('code')}: {payload.get('msg')}")
            return payload.get("data") if payload.get("data") is not None else {}
        return payload

    @staticmethod
    def _try_parse_business_error(resp: httpx.Response) -> dict | None:
        """SQLBot returns 500 + JSON for business errors. Detect envelope."""
        try:
            payload = resp.json()
        except Exception:
            return None
        if isinstance(payload, dict) and "success" in payload and "record_id" in payload:
            return payload
        return None

    # ----- 5 endpoints -----
    def login(self) -> str:
        data = self._request("POST", "/api/v1/mcp/access_token",
                             json_body={"username": self.cfg.username, "password": self.cfg.password})
        return data["access_token"]

    def start_session(self, token: str) -> tuple[str, int]:
        data = self._request("POST", "/api/v1/mcp/mcp_start",
                             token=token, token_in="body",
                             json_body={"token": token, "oid": self.cfg.workspace_id})
        return data.get("access_token") or token, int(data["chat_id"])

    def list_workspaces(self, token: str) -> list[dict]:
        return self._request("POST", "/api/v1/mcp/mcp_ws_list", token=token, token_in="query")

    def list_datasources(self, token: str) -> list[dict]:
        return self._request("POST", "/api/v1/mcp/mcp_ds_list", token=token, token_in="body")

    def ask(
        self,
        token: str,
        chat_id: int,
        question: str,
        datasource_id: int | None = None,
        lang: str = "zh-CN",
        return_img: bool = True,
    ) -> dict:
        body = {
            "token": token, "chat_id": chat_id, "question": question,
            "lang": lang, "stream": False, "return_img": return_img,
        }
        # NOTE: stream=False is intentional. SQLBot's stream=True returns pre-batched
        # markdown chunks and drops the structured fields/rows/chart payload we rely on
        # for table+chart rendering. See routes.ask_stream docstring (Task #70).
        if datasource_id is not None:
            body["datasource_id"] = datasource_id
        return self._request("POST", "/api/v1/mcp/mcp_question", json_body=body)

    # ----- Chart download -----
    def chart_bytes(self, image_url: str) -> bytes:
        url = image_url.replace("YOUR_SERVE_IP", "localhost").replace(
            "MCP_PORT", self.cfg.image_base.rsplit(":", 1)[-1].split("/", 1)[0]
        )
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as e:
            raise SqlBotTransientError(f"download chart failed: {e}") from e


# ---------- Helpers ----------
def decode_sql_b64(data: dict | None) -> str:
    """data.sql is base64-encoded SQL; decode to plaintext.

    Only decodes when the value is strict base64 (base64 alphabet + optional
    padding); otherwise returns it unchanged so already-plaintext SQL passes
    through intact (the function is not idempotent for arbitrary text).
    """
    if not data:
        return ""
    b64 = data.get("sql", "")
    if not b64:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", b64):
        return b64
    try:
        return base64.b64decode(b64, validate=True).decode("utf-8", errors="replace")
    except Exception:
        return b64


def parse_data_envelope(data: dict | None) -> tuple[list[str], list[dict]]:
    """data -> (fields, rows)."""
    if not data:
        return [], []
    return data.get("fields") or [], data.get("data") or []


__all__ = [
    "SqlBotConfig",
    "SqlBotClient",
    "SqlBotError",
    "SqlBotAuthError",
    "SqlBotTransientError",
    "decode_sql_b64",
    "parse_data_envelope",
]