"""Deprecated shim - re-exports from new locations.

This package is kept for backwards compatibility. The actual code now lives in:
- mini_agent.connectors.sqlbot   (SqlBotClient, SqlBotConfig, ...)
- mini_agent.memory.session      (SessionStore, Session, Message)
- mini_agent.render              (render_answer_md, ...)
"""
from ..connectors.sqlbot import (
    SqlBotClient,
    SqlBotConfig,
    SqlBotError,
    SqlBotAuthError,
    SqlBotTransientError,
    decode_sql_b64,
    parse_data_envelope,
)
from ..memory.session import (
    Message,
    Session,
    SessionStore,
)
from ..render import (
    describe_chart,
    download_chart,
    render_answer_md,
    render_from_data_envelope,
    render_markdown_table,
)

__all__ = [
    "SqlBotClient", "SqlBotConfig", "SqlBotError", "SqlBotAuthError", "SqlBotTransientError",
    "decode_sql_b64", "parse_data_envelope",
    "Message", "Session", "SessionStore",
    "render_answer_md", "render_from_data_envelope", "render_markdown_table",
    "describe_chart", "download_chart",
]
