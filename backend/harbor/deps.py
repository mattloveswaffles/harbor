"""FastAPI dependencies: session, clock, bank, settings and the X-User-Id user."""

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlmodel import Session

from harbor.bank import Bank, get_bank
from harbor.clock import Clock, get_clock
from harbor.config import Settings
from harbor.db import get_session
from harbor.errors import HarborError
from harbor.models import User


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[Session, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]
BankDep = Annotated[Bank, Depends(get_bank)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def user_from_credentials(session: Session, settings: Settings, authorization: str | None,
                          user_id: str | None) -> User:
    """A Bearer token from /auth/login or /auth/signup; or, in demo mode only, a bare user id."""
    from harbor.auth import user_for_token

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HarborError(401, "invalid_token", "Send the login token as: Authorization: Bearer <token>.")
        user = user_for_token(session, token.strip())
        if user is None:
            raise HarborError(401, "invalid_token", "Your login has expired or you logged out. Log in again.")
        return user
    if user_id:
        if settings.harbor_mode != "demo":
            raise HarborError(401, "auth_required", "Log in and send Authorization: Bearer <token>.")
        user = session.get(User, user_id)
        if user is None:
            raise HarborError(401, "user_not_found", "No user with this id. Sign up again or load the demo persona.")
        return user
    raise HarborError(401, "auth_required", "Log in and send Authorization: Bearer <token>.")


def get_current_user(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header(description="Bearer <token> from /auth/login or /auth/signup")] = None,
    x_user_id: Annotated[str | None, Header(description="Demo mode only: a user id from /demo/persona")] = None,
) -> User:
    return user_from_credentials(session, request.app.state.settings, authorization, x_user_id)


UserDep = Annotated[User, Depends(get_current_user)]


def require_demo(settings: SettingsDep) -> None:
    if settings.harbor_mode != "demo":
        raise HarborError(403, "demo_mode_only", "This endpoint only works when HARBOR_MODE=demo.")
