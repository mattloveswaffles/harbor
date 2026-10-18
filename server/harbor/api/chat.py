"""POST /me/chat: Ask Harbor, the agent with tools over the user's own data."""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from harbor.ai.agent import ChatDeps, check_rate, stream_reply
from harbor.ai.llm import model as llm_model
from harbor.deps import ClockDep, UserDep
from harbor.errors import HarborError
from harbor.models import User

router = APIRouter(tags=["chat"])
log = logging.getLogger("harbor.chat")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40, description="The conversation so far, oldest first")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/me/chat")
async def chat(body: ChatIn, request: Request, user: UserDep, clock: ClockDep) -> StreamingResponse:
    """Answer the last user turn as a stream of server-sent events: `thinking` and `text` deltas, a `tool` event
    per lookup, then `done` with `tools_used` (or `error`). 503 `chat_unavailable` without OPENROUTER_API_KEY."""
    if body.messages[-1].role != "user":
        raise HarborError(422, "validation_error", "The last message must be from the user.")
    model = llm_model(request.app)
    if model is None:
        raise HarborError(503, "chat_unavailable", "Ask Harbor needs an OPENROUTER_API_KEY on the server.")
    check_rate(request.app, user.id)
    turns = [(m.role, m.content) for m in body.messages]
    user_id = user.id

    async def events():
        with Session(request.app.state.engine) as session:  # lives as long as the stream, not the request
            deps = ChatDeps(request, session, session.get(User, user_id), clock)
            try:
                async for event in stream_reply(model, deps, turns):
                    yield _sse(event)
            except Exception as exc:
                log.warning("chat failed: %s", exc)
                yield _sse(
                    {"type": "error", "code": "chat_failed", "message": "Harbor couldn't answer right now. Try again."}
                )

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
