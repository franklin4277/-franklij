"""App state, initialized via FastAPI lifespan.

Holds the shared SqlBotClient + SessionStore singleton.
The 'service' object is a thin AskService wrapper.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI

from mini_agent.data_agent import (
    SessionStore,
    SqlBotClient,
    decode_sql_b64,
    render_answer_md,
)

import yaml as _yaml


# ---- light-weight config loader (no extra module needed) ----
def _load_config(yaml_path: str | None = None):
    """Load SqlBotConfig from yaml. Returns SqlBotConfig."""
    from mini_agent.connectors.sqlbot import SqlBotConfig

    candidates = []
    if yaml_path:
        candidates.append(Path(yaml_path))
    candidates += [
        Path("mini_agent/config/sqlbot.yaml"),
        Path("mini_agent/config/sqlbot-example.yaml"),
        Path.home() / ".mini-agent/config/sqlbot.yaml",
    ]
    for p in candidates:
        if p.exists():
            data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            sb = data.get("sqlbot", {})
            known = {"api_base", "image_base", "username", "password",
                     "workspace_id", "request_timeout", "auto_retry", "default_datasource_id"}
            return SqlBotConfig(**{k: v for k, v in sb.items() if k in known})
    return SqlBotConfig()

logger = logging.getLogger(__name__)


# ---- Thin service: wraps SqlBotClient + render + persist ----
@dataclass
class AskService:
    """Minimal ask service. Replaces the deleted QueryService."""

    sqlbot: SqlBotClient
    store: SessionStore

    async def ask(
        self,
        session_id: str,
        question: str,
        *,
        datasource_id: int | None = None,
        lang: str = "zh-CN",
        clarify: bool = False,
        summarize: bool = False,
    ) -> AskResult:
        """Run a query via SQLBot, render, and persist."""
        sess = self.store.get(session_id)
        ds = datasource_id if datasource_id is not None else sess.default_datasource_id

        # Call SQLBot
        raw = self.sqlbot.ask(
            token=sess.token,
            chat_id=sess.chat_id,
            question=question,
            datasource_id=ds,
            lang=lang,
        )

        # SQLBot returns data.sql base64-encoded; decode once at the boundary
        # (decode_sql_b64 is not idempotent, so it runs before render/persist)
        sql_text = decode_sql_b64(raw)
        raw = {**raw, "sql": sql_text}

        # Render
        answer_md, chart_path = render_answer_md(
            raw,
            charts_dir=sess.workspace / "charts",
            chart_bytes_fn=self.sqlbot.chart_bytes,
        )

        # Persist history (append_history calls _save internally;
        # sess.touch() updates last_used_at before the first save)
        sess.touch()
        self.store.append_history(sess.id, "user", question)
        self.store.append_history(sess.id, "assistant", answer_md, sql=sql_text)

        # Build result
        data = raw.get("data") or {}
        chart = raw.get("chart") or {}
        return AskResult(
            success=raw.get("success", False),
            answer_md=answer_md,
            sql=sql_text,
            chart_image_path=chart_path,
            message=raw.get("message"),
            record_id=raw.get("record_id"),
            fields=data.get("fields") or [],
            rows=data.get("data") or [],
            chart_type=chart.get("type"),
            chart_axis_x=(chart.get("axis") or {}).get("x", {}).get("name"),
            chart_axis_y=[(y or {}).get("name", "") for y in (chart.get("axis") or {}).get("y", [])],
        )


@dataclass
class AskResult:
    """Structured ask result."""
    success: bool
    answer_md: str = ""
    sql: str | None = None
    chart_image_path: str | None = None
    message: str | None = None
    clarification: str | None = None
    record_id: int | None = None
    fields: list[str] | None = None
    rows: list[dict] | None = None
    chart_type: str | None = None
    chart_axis_x: str | None = None
    chart_axis_y: list[str] | None = None


@dataclass
class AppState:
    """Process-wide singletons. Attached to app.state in lifespan."""

    sqlbot: SqlBotClient
    store: SessionStore
    service: AskService


def _make_state(workspace_dir: str | Path) -> AppState:
    cfg = _load_config(os.environ.get("SQLBOT_CONFIG"))
    sqlbot = SqlBotClient(cfg)
    store = SessionStore(sqlbot, workspace_dir)
    service = AskService(sqlbot=sqlbot, store=store)
    return AppState(sqlbot=sqlbot, store=store, service=service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    workspace_dir = Path(os.environ.get("WORKSPACE_DIR", "./workspace_api")).resolve()
    state = _make_state(workspace_dir)
    app.state.sqlbot = state.sqlbot
    app.state.store = state.store
    app.state.service = state.service
    logger.info(f"API ready: workspace={workspace_dir}")
    try:
        yield
    finally:
        state.sqlbot.close()
        logger.info("API shutdown")
