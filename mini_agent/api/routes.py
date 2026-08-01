"""API routes - single file.

Endpoints:
    GET    /health
    GET    /api/v1/datasets
    GET    /api/v1/workspaces
    POST   /api/v1/sessions
    GET    /api/v1/sessions/{id}
    DELETE /api/v1/sessions/{id}
    POST   /api/v1/sessions/{id}/ask
    POST   /api/v1/sessions/{id}/ask/stream   (SSE)
    GET    /api/v1/charts/{filename}
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .deps import AskResult, AskService
from mini_agent.data_agent import (
    SessionStore,
)
from mini_agent.core.events import (
    AgentStartedEvent,
    AgentStepEvent,
    AgentCompletedEvent,
    AgentErrorEvent,
)

from .models import (
    AskData,
    AskReq,
    AskResp,
    ChartInfo,
    CreateSessionReq,
    DatasourceItem,
    HealthResp,
    SessionResp,
    WorkspaceItem,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def _state(request: Request):
    return request.app.state


def _session_or_404(store: SessionStore, sid: str):
    try:
        return store.get(sid)
    except KeyError:
        raise HTTPException(404, f"session not found: {sid}")


def chart_image_url_for(chart_image_path: str | None) -> str | None:
    """Build the same-origin /api/v1/charts/<file> URL from a local chart path.

    Strips any directory component and normalizes Windows backslashes to
    forward slashes so the URL works regardless of where the chart was saved.
    Returns None if no path was provided.
    """
    if not chart_image_path:
        return None
    filename = chart_image_path.replace("\\", "/").rsplit("/", 1)[-1]
    return "/api/v1/charts/" + filename


def sse_data(event_type: str, payload: dict) -> str:
    """Format a dict payload as a single SSE event (single JSON encode)."""
    return "event: " + event_type + "\n" + "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _ask_to_resp(result: AskResult, session_id: str) -> AskResp:
    """Map QueryService.AskResult -> AskResp."""
    chart = None
    if result.success and result.chart_type:
        chart = ChartInfo(
            type=result.chart_type,
            axis_x=result.chart_axis_x,
            axis_y=result.chart_axis_y or [],
        )
    chart_url = None
    if result.chart_image_path:
        chart_url = chart_image_url_for(result.chart_image_path)
    return AskResp(
        success=result.success,
        session_id=session_id,
        sql=result.sql,
        record_id=result.record_id,
        chart=chart,
        chart_image_url=chart_url,
        message=result.message,
        clarification=result.clarification,
        data=AskData(
            fields=result.fields or [],
            rows=result.rows or [],
            row_count=len(result.rows or []),
        ),
    )


@router.get("/health", response_model=HealthResp, tags=["meta"])
async def health(request: Request) -> HealthResp:
    state = _state(request)
    reachable = False
    try:
        state.sqlbot.login()
        reachable = True
    except Exception:
        pass
    return HealthResp(
        status="ok",
        sqlbot_api=state.sqlbot.cfg.api_base,
        sqlbot_reachable=reachable,
    )


@router.get("/api/v1/datasets", response_model=list[DatasourceItem], tags=["catalog"])
async def list_datasets(request: Request) -> list[DatasourceItem]:
    state = _state(request)
    if not state.store.list_ids():
        state.store.create()
    sess = state.store.get(state.store.list_ids()[0])
    try:
        ds = state.sqlbot.list_datasources(sess.token)
    except Exception as e:
        raise HTTPException(503, f"SQLBot unreachable: {e}")
    return [
        DatasourceItem(id=d.get("id"), name=d.get("name"),
                       type=d.get("type"), type_name=d.get("type_name"))
        for d in ds
    ]


@router.get("/api/v1/workspaces", response_model=list[WorkspaceItem], tags=["catalog"])
async def list_workspaces(request: Request) -> list[WorkspaceItem]:
    state = _state(request)
    if not state.store.list_ids():
        state.store.create()
    sess = state.store.get(state.store.list_ids()[0])
    try:
        ws = state.sqlbot.list_workspaces(sess.token)
    except Exception as e:
        raise HTTPException(503, f"SQLBot unreachable: {e}")
    return [WorkspaceItem(id=w.get("id"), name=w.get("name")) for w in ws]


@router.post("/api/v1/sessions", response_model=SessionResp, tags=["sessions"])
async def create_session(req: CreateSessionReq | None, request: Request) -> SessionResp:
    state = _state(request)
    req = req or CreateSessionReq()
    sess = state.store.create(default_datasource_id=req.dataset_id)
    return SessionResp(
        id=sess.id,
        workspace_id=sess.workspace_id,
        default_datasource_id=sess.default_datasource_id,
        created_at=sess.created_at,
    )


@router.get("/api/v1/sessions/{session_id}", response_model=SessionResp, tags=["sessions"])
async def get_session(session_id: str, request: Request) -> SessionResp:
    state = _state(request)
    sess = _session_or_404(state.store, session_id)
    return SessionResp(
        id=sess.id,
        workspace_id=sess.workspace_id,
        default_datasource_id=sess.default_datasource_id,
        created_at=sess.created_at,
    )


@router.delete("/api/v1/sessions/{session_id}", tags=["sessions"])
async def destroy_session(session_id: str, request: Request) -> dict:
    state = _state(request)
    _session_or_404(state.store, session_id)
    state.store.destroy(session_id)
    return {"ok": True}


@router.post("/api/v1/sessions/{session_id}/ask", response_model=AskResp, tags=["ask"])
async def ask(session_id: str, req: AskReq, request: Request) -> AskResp:
    state = _state(request)
    service: AskService = state.service
    _session_or_404(state.store, session_id)
    result = await service.ask(
        session_id, req.question,
        datasource_id=req.datasource_id,
        lang=req.lang,
        clarify=False, summarize=False,
    )
    return _ask_to_resp(result, session_id)


@router.post("/api/v1/sessions/{session_id}/ask/stream", tags=["ask"])
async def ask_stream(session_id: str, req: AskReq, request: Request):
    """SSE stream: step-event pseudo-streaming (NOT token-level streaming).

    Emits a sequence of events so the client can show "working" feedback:
    started -> step -> completed (or error).

    We deliberately do NOT proxy SQLBot's stream=True protocol here. Investigation
    (Task #70, 2026-07-31) showed SQLBot's streaming is not true incremental output:
    it returns a handful of pre-batched markdown chunks (response-id, echoed question,
    full SQL block, table header, table rows) that arrive together, and crucially it
    DROPS the structured fields/rows/chart payload that stream=False provides. Forwarding
    those chunks would break the frontend table+chart rendering for no latency win.
    """
    state = _state(request)
    service: AskService = state.service
    _session_or_404(state.store, session_id)

    def sse(event) -> str:
        data = {k: v for k, v in vars(event).items() if v is not None and k != "timestamp"}
        return "event: " + event.type + "\n" + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

    async def generate():
        yield sse(AgentStartedEvent(task=req.question))
        yield sse(AgentStepEvent(
            step_number=1, description="Querying SQLBot",
            tool_name="sqlbot_ask", tool_args={"question": req.question},
        ))
        try:
            result = await service.ask(
                session_id, req.question,
                datasource_id=req.datasource_id,
                lang=req.lang,
                clarify=False, summarize=False,
            )
            preview = (result.answer_md or "")[:300]
            yield sse(AgentStepEvent(
                step_number=1, tool_name="sqlbot_ask",
                tool_result_preview=preview,
            ))
            chart_url = chart_image_url_for(result.chart_image_path)
            chart = None
            if result.success and result.chart_type:
                chart = {
                    "type": result.chart_type,
                    "axis_x": result.chart_axis_x,
                    "axis_y": result.chart_axis_y or [],
                }
            # Emit raw payload (not double-encoded via AgentCompletedEvent.final_result)
            yield sse_data("completed", {
                "success": result.success,
                "answer_md": result.answer_md,
                "sql": result.sql,
                "record_id": result.record_id,
                "clarification": result.clarification,
                "chart": chart,
                "chart_image_url": chart_url,
                "fields": result.fields,
                "rows": result.rows,
                "row_count": len(result.rows or []),
                "message": result.message,
            })
        except Exception as e:
            yield sse(AgentErrorEvent(error=str(e), recoverable=False))

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/api/v1/charts/{filename}", tags=["charts"])
async def chart(filename: str, request: Request):
    """Proxy SQLBot static /images/ as same-origin."""
    if not filename or _SAFE_FILENAME.sub("", filename) != filename:
        raise HTTPException(400, "invalid filename")
    state = _state(request)
    try:
        url = state.sqlbot.cfg.image_base.rstrip("/") + "/images/" + filename
        content = state.sqlbot.chart_bytes(url)
    except Exception as e:
        raise HTTPException(404, f"chart not available: {e}")
    from fastapi.responses import Response
    return Response(content=content, media_type="image/png")
