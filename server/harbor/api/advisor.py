"""GET /me/advice and POST /me/advice/regenerate: the evacuation advice on My plan."""

from fastapi import APIRouter, Request

from harbor.ai import advisor
from harbor.deps import SessionDep, UserDep

router = APIRouter(tags=["advice"])


@router.get("/me/advice")
def get_advice(request: Request, user: UserDep, session: SessionDep) -> dict:
    """The AI's advice when it matches the latest data, else Harbor's rules. `status` is running while the AI works."""
    return advisor.current(request.app, session, user)


@router.post("/me/advice/regenerate", status_code=202)
def regenerate(request: Request, user: UserDep, session: SessionDep) -> dict:
    return advisor.regenerate(request.app, session, user)
