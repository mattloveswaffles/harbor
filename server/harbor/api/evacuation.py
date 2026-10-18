"""GET /me/evacuation and POST /me/evacuation/destination: where to go, how, and where to stay."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from harbor.context import evacuation_for, storm_inputs
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.errors import HarborError
from harbor.evac.atms import rank_atms
from harbor.evac.destination import _to_shape, load_destinations

router = APIRouter(tags=["evacuation"])


class DestinationIn(BaseModel):
    destination_id: str


@router.get("/me/evacuation")
def get_evacuation(request: Request, session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    """The evacuation guide, or `{"guide": null}` before the user reaches prepare."""
    bundle = evacuation_for(request.app, session, user, clock.now())
    return bundle["guide"] if bundle else {"guide": None}


@router.get("/me/atms")
def get_atms(
    request: Request,
    session: SessionDep,
    user: UserDep,
    clock: ClockDep,
    radius_miles: float = Query(150, gt=0, le=500),
) -> list[dict]:
    """ATMs: outside the cone and on the route first, then by distance."""
    now = clock.now()
    bundle = evacuation_for(request.app, session, user, now)
    if bundle and radius_miles == 150:
        return bundle["atms"]
    cone = _to_shape(storm_inputs(request.app, user, now)["cone"])
    route = (
        bundle["layers"]["route"]["features"][0]["geometry"]
        if bundle and bundle["layers"]["route"]["features"]
        else None
    )
    return rank_atms((user.lat, user.lon), radius_miles, cone=cone, route_geometry=route)


@router.post("/me/evacuation/destination")
def choose_destination(
    body: DestinationIn, request: Request, session: SessionDep, user: UserDep, clock: ClockDep
) -> dict:
    """Choose a destination; the route, lodging and plan budget follow."""
    if body.destination_id not in {d.id for d in load_destinations()}:
        raise HarborError(404, "destination_not_found", "Unknown destination id.")
    previous = dict(user.settings or {})
    user.settings = {**previous, "evac_destination": body.destination_id}
    now = clock.now()
    bundle = evacuation_for(request.app, session, user, now)
    if bundle and bundle["guide"]["chosen"] != body.destination_id:
        user.settings = previous
        raise HarborError(
            409,
            "destination_not_safe",
            "That destination isn't available right now (it may be inside the forecast cone).",
        )
    session.add(user)
    session.commit()
    return bundle["guide"] if bundle else {"guide": None}
