"""GET /me/sensors and /me/sensors/{id}/history: the tide gauges, river gauges and buoys near home."""

from fastapi import APIRouter, Query, Request

from harbor.context import sensors_for
from harbor.deps import ClockDep, UserDep
from harbor.errors import HarborError

router = APIRouter(tags=["sensors"])


@router.get("/me/sensors")
def get_sensors(request: Request, user: UserDep, clock: ClockDep,
                radius_miles: float = Query(200, gt=0, le=500)) -> list[dict]:
    """Sensor readings closest first, each with normal/watch/warning/stale and the reason."""
    sensors = sensors_for(request.app)
    readings = sensors.readings(clock.now(), user.lat, user.lon, radius_miles) if sensors else []
    return [r.to_api() for r in readings]


@router.get("/me/sensors/{sensor_id}/history")
def get_sensor_history(request: Request, sensor_id: str, user: UserDep, clock: ClockDep,
                       hours: int = Query(48, gt=0, le=336),
                       metrics: str | None = Query(None, description="Comma-separated reading keys, e.g. surge_ft,stage_ft")) -> list[dict]:
    """Readings over the last `hours`, ready for a chart. The replay never returns future rows."""
    now = clock.now()
    sensors = sensors_for(request.app)
    if sensors is None or not any(s.station.id == sensor_id for s in sensors.series):
        raise HarborError(404, "sensor_not_found", "No sensor with this id in the current storm.")
    wanted = [m.strip() for m in metrics.split(",")] if metrics else None
    return sensors.history(sensor_id, now, hours, wanted)
