"""Accounts: POST /auth/signup, /auth/login, /auth/logout and GET /auth/me.

Send the returned token on every request as `Authorization: Bearer <token>` (the live stream
takes it as `?token=`, because EventSource can't send headers).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import select

from harbor.auth import LoginLimiter, check_login, hash_password, issue_token, normalize_email, revoke_token
from harbor.clock import iso
from harbor.deps import BankDep, ClockDep, SessionDep, UserDep, require_demo
from harbor.errors import HarborError
from harbor.models import Credential
from harbor.schemas import CreateUser, UserOut
from harbor.seed import seed_persona

from harbor.api.users import new_user, user_out

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", examples=["maria@example.com"])


class SignupIn(CreateUser):
    email: str = EMAIL
    password: str = Field(min_length=8, max_length=128, description="At least 8 characters")


class LoginIn(BaseModel):
    email: str = EMAIL
    password: str = Field(min_length=1, max_length=128)


class AuthOut(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserOut


def limiter(request: Request) -> LoginLimiter:
    if not hasattr(request.app.state, "login_limiter"):
        request.app.state.login_limiter = LoginLimiter()
    return request.app.state.login_limiter


@router.post("/signup", response_model=AuthOut, status_code=201)
async def signup(body: SignupIn, session: SessionDep, bank: BankDep, clock: ClockDep) -> AuthOut:
    """Create an account. Your email and password stay in Harbor; Nessie only sees a pseudonym."""
    email = normalize_email(body.email)
    if session.exec(select(Credential).where(Credential.email == email)).first():
        raise HarborError(409, "email_taken", "An account with this email already exists. Log in instead.",
                          {"email": "Already registered"})
    user = await new_user(CreateUser(**body.model_dump(include={"name", "zip", "location", "household"})),
                          session, bank, clock.now())
    session.add(Credential(user_id=user.id, email=email, password_hash=hash_password(body.password),
                           created_at=clock.now()))
    token, expires = issue_token(session, user)
    session.commit()
    session.refresh(user)
    return AuthOut(token=token, expires_at=iso(expires), user=user_out(session, user))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, session: SessionDep) -> AuthOut:
    lim = limiter(request)
    if lim.locked(body.email):
        raise HarborError(429, "too_many_attempts", "Too many wrong passwords. Wait 15 minutes and try again.")
    user = check_login(session, body.email, body.password)
    if user is None:
        lim.failed(body.email)
        raise HarborError(401, "invalid_credentials", "That email and password don't match an account.")
    lim.succeeded(body.email)
    token, expires = issue_token(session, user)
    session.commit()
    return AuthOut(token=token, expires_at=iso(expires), user=user_out(session, user))


@router.post("/logout", status_code=204)
def logout(session: SessionDep, user: UserDep,
           authorization: Annotated[str | None, Header()] = None) -> Response:
    """End this login: the token stops working at once."""
    if authorization and authorization.lower().startswith("bearer "):
        revoke_token(session, authorization[7:].strip())
        session.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(session: SessionDep, user: UserDep) -> UserOut:
    return user_out(session, user)


@router.post("/demo-login", response_model=AuthOut, dependencies=[Depends(require_demo)])
async def demo_login(session: SessionDep, bank: BankDep, clock: ClockDep, persona: str = "maria") -> AuthOut:
    """Demo only: a login token for a demo persona (maria or ruth), so the website can use the same
    Bearer login for judges as for real users."""
    if persona not in ("maria", "ruth"):
        raise HarborError(404, "persona_not_found", "Personas are maria and ruth.")
    user = await seed_persona(session, bank, clock.now(), persona)
    token, expires = issue_token(session, user)
    session.commit()
    return AuthOut(token=token, expires_at=iso(expires), user=user_out(session, user))
