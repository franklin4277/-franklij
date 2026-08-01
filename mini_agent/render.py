"""Render SQLBot query results — Markdown tables + chart descriptions.

Public API:
    render_markdown_table: format rows as Markdown table
    render_from_data_envelope: from SQLBot's {fields, data} envelope
    render_answer_md: full answer (title + table + chart + SQL + message)
    describe_chart: human-readable ECharts config
    download_chart: save chart PNG to workspace
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


# ---------- Table ----------
def render_markdown_table(
    fields: list[str],
    rows: list[dict],
    *,
    max_rows: int = 50,
    title: str | None = None,
) -> str:
    """Format rows as Markdown table. Truncates to max_rows."""
    if not fields:
        return "(空结果：没有字段)"

    lines: list[str] = []
    if title:
        lines.append(f"**{title}**")
        lines.append("")
    lines.append("| " + " | ".join(str(f) for f in fields) + " |")
    lines.append("| " + " | ".join("---" for _ in fields) + " |")

    for row in rows[:max_rows]:
        cells = [_cell(row.get(f, "")) for f in fields]
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > max_rows:
        lines.append(f"\n*（仅显示前 {max_rows} 行，共 {len(rows)} 行）*")
    return "\n".join(lines)


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


def render_from_data_envelope(
    data: dict | None, *, max_rows: int = 50, title: str | None = None
) -> str:
    """Convenience: take SQLBot's `data` field directly."""
    if not data:
        return "(无数据)"
    fields = data.get("fields") or []
    rows = data.get("data") or []
    return render_markdown_table(fields, rows, max_rows=max_rows, title=title)


# ---------- Chart ----------
def describe_chart(chart: dict | None) -> str:
    """Human-readable ECharts config summary."""
    if not chart:
        return ""
    ctype = chart.get("type", "unknown")
    title = chart.get("title", "")
    axis = chart.get("axis") or {}
    x = (axis.get("x") or {}).get("name", "")
    y_list = axis.get("y") or []
    y_names = ", ".join((y or {}).get("name", "?") for y in y_list)
    parts = [f"图表类型: {ctype}"]
    if title:
        parts.append(f"标题: {title}")
    if x:
        parts.append(f"X 轴: {x}")
    if y_names:
        parts.append(f"Y 轴: {y_names}")
    return " | ".join(parts)


def download_chart(
    image_url: str,
    workspace_dir: str | Path,
    *,
    chart_bytes_fn: Callable[[str], bytes],
) -> str:
    """Download chart PNG via callback; save to workspace/charts/. Return path."""
    if not image_url:
        return ""
    base = image_url.rsplit("/", 1)[-1]
    base = _SAFE_NAME.sub("_", base) or "chart.png"
    if not base.endswith(".png"):
        base += ".png"
    charts_dir = Path(workspace_dir) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    out_path = charts_dir / base
    try:
        out_path.write_bytes(chart_bytes_fn(image_url))
        logger.info(f"chart saved: {out_path} ({out_path.stat().st_size} bytes)")
        return str(out_path)
    except Exception as e:
        logger.warning(f"chart download failed: {e}")
        return ""


# ---------- Full answer ----------
def render_answer_md(
    raw: dict,
    *,
    charts_dir: Path,
    chart_bytes_fn: Callable[[str], bytes],
) -> tuple[str, str | None]:
    """Render the full answer Markdown from a SQLBot ask response.

    Returns (markdown, chart_path_or_None).
    """
    success = bool(raw.get("success"))
    title = raw.get("title") or ""
    sql = raw.get("sql") or ""
    data = raw.get("data") or {}
    chart = raw.get("chart") or {}
    image_url = raw.get("image_url") or ""
    message = raw.get("message") or ""

    parts: list[str] = []
    if title:
        parts.append(f"**{title}**\n")

    if success and data:
        parts.append(render_from_data_envelope(data, title=None))

    if chart:
        desc = describe_chart(chart)
        if desc:
            parts.append(f"\n{desc}")

    chart_path: str | None = None
    if image_url:
        chart_path = download_chart(image_url, charts_dir, chart_bytes_fn=chart_bytes_fn)
        if chart_path:
            parts.append(f"\n图表已保存: `{chart_path}`")
        else:
            parts.append(f"\n(图表下载失败: {image_url})")

    if sql:
        parts.append(f"\nSQL:\n```sql\n{sql}\n```")
    if not success and message:
        parts.append(f"\n失败原因: {message}")

    return "\n".join(parts), chart_path


__all__ = [
    "render_markdown_table",
    "render_from_data_envelope",
    "describe_chart",
    "download_chart",
    "render_answer_md",
]