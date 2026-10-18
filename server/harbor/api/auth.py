"""POST /auth/signup, /auth/login and /auth/logout. Send `Authorization: Bearer <token>` (`?token=` for the SSE
stream).
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import select

from harbor.api.users import new_user, user_out
from harbor.auth import check_login, hash_password, issue_token, normalize_email, revoke_token
from harbor.clock import iso
from harbor.deps import BankDep, ClockDep, SessionDep, UserDep
from harbor.errors import HarborError
from harbor.models import Credential
from harbor.schemas import CreateUser, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# An email, or a short username like the demo account's "demo"
LOGIN = Field(
    min_length=3,
    max_length=254,
    pattern=r"^([^@\s]+@[^@\s]+\.[^@\s]+|[\w.-]{3,32})$",
    examples=["maria@example.com", "demo"],
)


class SignupIn(CreateUser):
    email: str = LOGIN
    password: str = Field(min_length=4, max_length=128, description="At least 4 characters")


class LoginIn(BaseModel):
    email: str = LOGIN
    password: str = Field(min_length=1, max_length=128)


class AuthOut(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserOut


@router.post("/signup", response_model=AuthOut, status_code=201)
async def signup(body: SignupIn, session: SessionDep, bank: BankDep, clock: ClockDep) -> AuthOut:
    """Create an account. Your email and password stay in Harbor; Nessie only sees a pseudonym."""
    email = normalize_email(body.email)
    if session.exec(select(Credential).where(Credential.email == email)).first():
        raise HarborError(
            409,
            "email_taken",
            "An account with this email already exists. Log in instead.",
            {"email": "Already registered"},
        )
    user = await new_user(body, session, bank, clock.now())
    session.add(
        Credential(user_id=user.id, email=email, password_hash=hash_password(body.password), created_at=clock.now())
    )
    token, expires = issue_token(session, user)
    session.commit()
    session.refresh(user)
    return AuthOut(token=token, expires_at=iso(expires), user=user_out(session, user))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, session: SessionDep) -> AuthOut:
    lim = request.app.state.login_limiter
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
def logout(session: SessionDep, user: UserDep, authorization: Annotated[str, Header()]) -> Response:
    """End this login: the token stops working at once."""
    revoke_token(session, authorization.partition(" ")[2].strip())
    session.commit()
    return Response(status_code=204)
