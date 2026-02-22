"""FastAPI application for the Gateway API."""

import asyncio
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from mini_agent.gateway.schemas import (
    CreateSessionRequest,
    SessionResponse,
    ChatRequest,
    ChatResponse,
    HistoryResponse,
)
from mini_agent.gateway.service import session_manager

app = FastAPI(
    title="Mini-Agent Gateway",
    description="HTTP API Gateway for Mini-Agent",
    version="0.1.0",
)

@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new agent session."""
    try:
        session_info = await session_manager.create_session(
            workspace_dir=request.workspace_dir,
            system_prompt=request.system_prompt
        )
        return SessionResponse(**session_info)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session information."""
    info = session_manager.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**info)

@app.delete("/sessions/{session_id}")
async def close_session(session_id: str):
    """Close a session."""
    if not session_manager.close_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed"}

@app.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    """Send a message to the agent."""
    agent = session_manager.get_agent(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Add user message
    agent.add_user_message(request.message)

    try:
        # Run agent (single turn or until completion)
        # Note: agent.run() runs until task completion or max steps
        # For a chat API, we might want single turn, but agent.run() is designed for tasks.
        # Let's use agent.run() as it handles tool calls automatically.
        response_content = await agent.run()
        
        # Get usage stats
        usage = {"total_tokens": agent.api_total_tokens}
        
        # Get tool calls from the last assistant message(s)
        # This is a simplification; we might want all tool calls in this run.
        tool_calls = []
        for msg in reversed(agent.messages):
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                        "id": tc.id
                    })
            if msg.role == "user" and msg.content == request.message:
                break # Stop when we reach the user's message

        return ChatResponse(
            response=response_content,
            tool_calls=tool_calls,
            usage=usage
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

@app.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_history(session_id: str):
    """Get chat history."""
    agent = session_manager.get_agent(session_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = []
    for msg in agent.messages:
        messages.append({
            "role": msg.role,
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None,
            "name": msg.name,
            "tool_call_id": msg.tool_call_id
        })

    return HistoryResponse(messages=messages)

def start_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Start the uvicorn server."""
    import uvicorn
    uvicorn.run("mini_agent.gateway.app:app", host=host, port=port, reload=reload)
