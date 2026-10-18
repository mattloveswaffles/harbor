"""GET/PUT /me/profile: the Settings popup. Saving it refreshes the household and the evacuation advice."""

from fastapi import APIRouter
from pydantic import Field

from harbor import profile
from harbor.api.users import zip_or_400
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.schemas import Location

router = APIRouter(tags=["profile"])


class ProfileIn(profile.ProfileData):
    zip: str | None = Field(default=None, pattern=r"^\d{5}$", description="New home ZIP, with `location`")
    location: Location | None = Field(default=None, description="Exact home location from the address search")


@router.get("/me/profile", response_model=profile.ProfileData)
def get_profile(user: UserDep, session: SessionDep) -> profile.ProfileData:
    return profile.load(session, user)


@router.put("/me/profile", response_model=profile.ProfileData)
def put_profile(body: ProfileIn, user: UserDep, session: SessionDep, clock: ClockDep):
    """Replace the profile. A new address moves the home."""
    if body.zip and body.zip != user.zip:
        place = zip_or_400(body.zip)
        user.zip, user.lat, user.lon, user.location_source = body.zip, place["lat"], place["lon"], "zcta"
    if body.location:
        user.lat, user.lon, user.location_source = body.location.lat, body.location.lon, "gps"
    data = profile.ProfileData.model_validate(body.model_dump(exclude={"zip", "location"}))
    profile.save(session, user, data, clock.now())
    session.commit()
    return data
