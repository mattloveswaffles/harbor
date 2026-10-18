"""GET /me/sensors: the tide gauges, river gauges and buoys near home."""

from fastapi import APIRouter, Query, Request

from harbor.context import sensors_for
from harbor.deps import ClockDep, UserDep

router = APIRouter(tags=["sensors"])


@router.get("/me/sensors")
def get_sensors(
    request: Request, user: UserDep, clock: ClockDep, radius_miles: float = Query(200, gt=0, le=500)
) -> list[dict]:
    """Sensor readings closest first, each with normal/watch/warning/stale and the reason."""
    sensors = sensors_for(request.app)
    readings = sensors.readings(clock.now(), user.lat, user.lon, radius_miles) if sensors else []
    return [r.to_api() for r in readings]
