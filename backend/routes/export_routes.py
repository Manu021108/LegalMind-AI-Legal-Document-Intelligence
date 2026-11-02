"""
Export Routes.
Handles exporting sessions as downloadable markdown files.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from backend.services.session_manager import get_session_by_id, get_full_history
from backend.utils.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["Export"])


@router.get("/{session_id}/export")
@limiter.limit("20/minute")
async def export_session_markdown(request: Request, session_id: str):
    """Export a session's full conversation as a downloadable Markdown file."""
    session = await asyncio.to_thread(get_session_by_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await asyncio.to_thread(get_full_history, session_id)

    # Build markdown
    lines = [
        f"# {session['title']}",
        f"",
        f"*Exported from Legal Document Analyzer*  ",
        f"*Session created: {session['created_at']}*",
        f"",
        f"---",
        f"",
    ]

    for msg in messages:
        role_label = "**You**" if msg["role"] == "user" else "**Legal Document Analyzer AI**"
        lines.append(f"### {role_label}")
        lines.append(f"")
        lines.append(msg["content"])
        lines.append(f"")

        # Add source citations for assistant messages
        sources = msg.get("sources", [])
        if sources:
            lines.append(f"*Sources:*")
            for src in sources:
                relevance = round(src.get("relevance", 0) * 100)
                lines.append(f"- 📄 {src.get('doc_name', 'Unknown')} · Page {src.get('page_number', '?')} ({relevance}% relevance)")
            lines.append(f"")

        lines.append(f"---")
        lines.append(f"")

    markdown_content = "\n".join(lines)

    # Return as downloadable file
    safe_title = "".join(c for c in session["title"] if c.isalnum() or c in " _-").strip()[:50] or "chat_export"
    filename = f"{safe_title}.md"

    return PlainTextResponse(
        content=markdown_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
