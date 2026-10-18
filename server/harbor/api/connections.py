"""Connected banks, brokerages and wallets, each backed by Nessie accounts."""

from fastapi import APIRouter, Path

from harbor import connections
from harbor.deps import BankDep, ClockDep, SessionDep, UserDep
from harbor.errors import HarborError

router = APIRouter(tags=["connections"])
InstitutionId = Path(examples=["chase"], description="One of " + ", ".join(connections.INSTITUTIONS))


def _known(institution: str) -> str:
    if institution not in connections.INSTITUTIONS:
        raise HarborError(404, "not_found", f"Harbor doesn't connect to {institution!r}.")
    return institution


@router.get("/me/connections")
def list_connections(user: UserDep, session: SessionDep) -> list[dict]:
    return connections.listing(session, user)


@router.post("/me/connections/{institution}")
async def connect(
    user: UserDep,
    session: SessionDep,
    bank: BankDep,
    clock: ClockDep,
    institution: str = InstitutionId,
) -> list[dict]:
    """Connect through Nessie: the bank links checking and savings, wallets open an account with a mock balance."""
    await connections.connect(session, bank, user, _known(institution), clock.now())
    session.commit()
    return connections.listing(session, user)


@router.delete("/me/connections/{institution}")
async def disconnect(
    user: UserDep,
    session: SessionDep,
    bank: BankDep,
    clock: ClockDep,
    institution: str = InstitutionId,
) -> list[dict]:
    await connections.disconnect(session, bank, user, _known(institution), clock.now())
    session.commit()
    return connections.listing(session, user)
