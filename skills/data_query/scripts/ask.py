"""data_query skill - high-level ask via SqlBotConnector.

Hides SQLBot's token/chat_id complexity from the LLM.
Drop-in: call ask(question, datasource_id), get structured result + Markdown.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

WORKSPACE_DIR = Path(os.environ.get("MINI_AGENT_WORKSPACE", "./workspace"))
CHARTS_DIR = WORKSPACE_DIR / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


async def ask(
    question: str,
    datasource_id: int | None = None,
) -> dict:
    """Run a data query via SQLBot.

    Returns dict with: success, answer_md, sql, chart_path, record_id, row_count, message.
    """
    from mini_agent.connectors.sqlbot import SqlBotClient, SqlBotConfig
    from mini_agent.render import render_answer_md

    cfg = SqlBotConfig(
        api_base=os.environ.get("SQLBOT_API_BASE", "http://localhost:18000"),
        image_base=os.environ.get("SQLBOT_IMAGE_BASE", "http://localhost:18001"),
        username=os.environ.get("SQLBOT_USERNAME", "admin"),
        password=os.environ.get("SQLBOT_PASSWORD", "SQLBot@123456"),
    )

    try:
        with SqlBotClient(cfg) as client:
            token = client.login()
            token, chat_id = client.start_session(token)
            raw = client.ask(
                token=token, chat_id=chat_id,
                question=question, datasource_id=datasource_id,
            )

        answer_md, chart_path = render_answer_md(
            raw,
            charts_dir=CHARTS_DIR,
            chart_bytes_fn=lambda url: _download_chart(url, cfg),
        )
        data = raw.get("data") or {}
        return {
            "success": raw.get("success", False),
            "answer_md": answer_md,
            "sql": raw.get("sql"),
            "chart_path": chart_path,
            "record_id": raw.get("record_id"),
            "row_count": len(data.get("data") or []),
            "message": raw.get("message", ""),
        }
    except Exception as e:
        logger.exception("ask failed")
        return {"success": False, "message": str(e), "answer_md": f"❌ {e}"}


def _download_chart(image_url: str, cfg) -> bytes:
    import httpx
    url = image_url.replace("YOUR_SERVE_IP", "localhost").replace(
        "MCP_PORT", cfg.image_base.rsplit(":", 1)[-1].split("/", 1)[0]
    )
    return httpx.Client(timeout=30).get(url).content


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


if __name__ == "__main__":
    import asyncio
    if len(sys.argv) < 2:
        print("Usage: python ask.py <question> [datasource_id]")
        sys.exit(1)
    ds_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    result = asyncio.run(ask(sys.argv[1], ds_id))
    print(result["answer_md"])
    sys.exit(0 if result["success"] else 1)
