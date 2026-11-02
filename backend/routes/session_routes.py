"""
Session Routes.
Handles conversation session management — create, list, get, delete.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

from backend.services.session_manager import (
    create_session, list_all_sessions,
    get_session_by_id, get_full_history,
    delete_session
)
from backend.utils.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


class CreateSessionRequest(BaseModel):
    """Request body for creating a new session."""
    title: Optional[str] = Field(default="New Chat", max_length=200)


@router.post("")
@limiter.limit("30/minute")
async def create_new_session(request: Request, body: CreateSessionRequest):
    """Create a new conversation session."""
    session = await asyncio.to_thread(create_session, body.title)
    return session


@router.get("")
async def list_sessions():
    """List all conversation sessions with previews."""
    sessions = await asyncio.to_thread(list_all_sessions)
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session_detail(session_id: str):
    """Get a session with its full message history."""
    session = await asyncio.to_thread(get_session_by_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await asyncio.to_thread(get_full_history, session_id)

    return {
        **session,
        "messages": messages,
    }


@router.delete("/{session_id}")
@limiter.limit("30/minute")
async def delete_session_endpoint(request: Request, session_id: str):
    """Delete a session and all its messages."""
    session = await asyncio.to_thread(get_session_by_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await asyncio.to_thread(delete_session, session_id)
    return {"message": "Session deleted successfully"}
