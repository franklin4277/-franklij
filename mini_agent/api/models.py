"""Pydantic models for the data agent HTTP API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ----- Requests -----
class CreateSessionReq(BaseModel):
    dataset_id: int | None = None


class AskReq(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    datasource_id: int | None = None
    lang: Literal["zh-CN", "zh-TW", "en", "ko-KR"] = "zh-CN"


# ----- Responses -----
class HealthResp(BaseModel):
    status: str
    sqlbot_api: str
    sqlbot_reachable: bool


class DatasourceItem(BaseModel):
    id: int
    name: str
    type: str | None = None
    type_name: str | None = None


class WorkspaceItem(BaseModel):
    id: int
    name: str


class SessionResp(BaseModel):
    id: str
    workspace_id: str
    default_datasource_id: int | None = None
    created_at: str


class ChartInfo(BaseModel):
    type: str | None = None
    axis_x: str | None = None
    axis_y: list[str] = Field(default_factory=list)


class AskData(BaseModel):
    fields: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0


class AskResp(BaseModel):
    success: bool
    session_id: str
    record_id: int | None = None
    sql: str | None = None
    data: AskData
    chart: ChartInfo | None = None
    chart_image_url: str | None = None
    message: str | None = None
    clarification: str | None = None