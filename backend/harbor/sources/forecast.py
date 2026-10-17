"""NHC cone, track, wind probabilities and arrival times, plus NWS/IEM alerts, for a ZIP.

`ReplaySource` reads a replay built by `tools/fetch_replay.py` (data/replays/<storm>/) and answers
"what did the forecast say at time `now`": the newest advisory with `issued_at <= now`, and the
alerts in force at `now`. A live source (NHC + NWS) will implement the same methods, so the risk
engine and the API can't tell the two apart.

Point lookups (all in lon/lat; small distances use a local equirectangular projection):
- in_cone: the cone polygon, buffered by 0.1° (the cone is track error, not a wind footprint).
- p34 / p64: bilinear interpolation on the half-degree grid, clamped into the 5 km band that
  contains the point (bands are read with the even-odd rule).
- eta: the earliest reasonable arrival of tropical-storm winds, interpolated between the two
  nearest isochrones of the arrival-time product; null outside its 5% ring. Without that product,
  a rough estimate from when the forecast centre comes within 100 miles.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cached_property, lru_cache
from pathlib import Path

from shapely import prepared
from shapely.geometry import LineString, Point, Polygon, shape

from harbor.clock import iso, utc

CONE_BUFFER_DEG = 0.1
ESTIMATE_RADIUS_KM = 160  # about 100 miles: a typical tropical-storm wind radius for a large hurricane
KT_TO_MPH = 1.15078


def parse_time(s: str) -> datetime:
    return utc(datetime.fromisoformat(s.replace("Z", "+00:00")))


@lru_cache(maxsize=256)
def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Advisory:
    adv: str                      # "015", "015A"
    advisory_number: str          # "15", "15A"
    issued_at: datetime
    intermediate: bool
    classification: str           # hurricane, tropical_storm, ...
    category: int | None
    lat: float
    lon: float
    max_wind_kt: int | None
    pressure_mb: int | None
    headline: str | None
    file: str
    wsp: str | None
    toa: str | None
    products_from: str | None

    @property
    def max_wind_mph(self) -> int | None:
        return round(self.max_wind_kt * KT_TO_MPH) if self.max_wind_kt is not None else None


@dataclass(frozen=True)
class Exposure:
    """What the forecast says about one point at one moment."""

    advisory: Advisory | None
    p34: float = 0.0
    p64: float = 0.0
    in_cone: bool = False
    eta: datetime | None = None
    eta_source: str | None = None  # toa_kmz | estimate (pws_text is not built yet)
    alerts: list[dict] = field(default_factory=list)

    @property
    def alert_types(self) -> frozenset[str]:
        return frozenset(a["type"] for a in self.alerts)

    def out(self) -> dict:
        """The `at_your_zip` object of GET /me/storm."""
        return {
            "ts_wind_probability_5day": round(self.p34, 2),
            "hurricane_wind_probability_5day": round(self.p64, 2),
            "in_forecast_cone": self.in_cone,
            "earliest_ts_winds_eta": iso(self.eta),
            "eta_source": self.eta_source,
            "alerts": [{k: a[k] for k in ("type", "headline", "issued", "expires", "source")} for a in self.alerts],
        }


class _Wsp:
    """One wind speed probability file: grid lookup + band clamp."""

    def __init__(self, data: dict):
        self.step = data.get("grid_step_deg", 0.5)
        self.clip_box = data.get("clip_box")
        self.grid = {kt: {(round(lon / self.step), round(lat / self.step)): v for lon, lat, v in cells}
                     for kt, cells in data["grid"].items()}
        self.bands = {
            kt: [(b["lo"], b["hi"], [prepared.prep(Polygon(r)) for r in b["rings"]]) for b in bands]
            for kt, bands in data["bands"].items()
        }

    def prob_at(self, lon: float, lat: float, kt: str) -> float:
        grid = self.grid.get(kt, {})
        fx, fy = lon / self.step, lat / self.step
        x0, y0 = math.floor(fx), math.floor(fy)
        tx, ty = fx - x0, fy - y0
        v = sum(
            grid.get((x0 + dx, y0 + dy), 0.0) * (tx if dx else 1 - tx) * (ty if dy else 1 - ty)
            for dx in (0, 1)
            for dy in (0, 1)
        )
        bands = self.bands.get(kt)
        if not bands or not self._in_clip(lon, lat):
            return min(max(v, 0.0), 1.0)
        pt = Point(lon, lat)
        for lo, hi, rings in bands:
            if sum(r.contains(pt) for r in rings) % 2 == 1:
                return min(max(v, lo), hi)
        return min(v, bands[0][0] if bands[0][0] > 0 else 0.05)  # outside every band: below the lowest

    def _in_clip(self, lon: float, lat: float) -> bool:
        if not self.clip_box:
            return True
        x0, y0, x1, y1 = self.clip_box
        return x0 <= lon <= x1 and y0 <= lat <= y1


class _Toa:
    """Earliest-reasonable arrival isochrones."""

    def __init__(self, data: dict):
        self.published_at = parse_time(data["published_at"])
        self.lines = [(parse_time(i["time"]), i["coordinates"]) for i in data["isochrones"]]
        self.lines.sort(key=lambda x: x[0])
        self.ring5 = prepared.prep(Polygon(data["ring5"])) if data.get("ring5") else None

    def eta_at(self, lon: float, lat: float, centre: tuple[float, float], now: datetime) -> datetime | None:
        if not self.lines:
            return None
        if self.ring5 is not None and not self.ring5.contains(Point(lon, lat)):
            return None
        k = math.cos(math.radians(lat))  # local equirectangular projection around the point

        def proj(c):
            return ((c[0] - lon) * k, c[1] - lat)

        here = Point(0.0, 0.0)
        dists = [LineString([proj(c) for c in coords]).distance(here) for _, coords in self.lines]
        i = min(range(len(dists)), key=dists.__getitem__)
        t_i = self.lines[i][0]
        if i == 0:
            first = LineString([proj(c) for c in self.lines[0][1]])
            storm = Point(proj(centre))
            if storm.distance(here) < first.distance(storm):
                return _floor_hour(min(t_i, now))  # between the storm and the first line
        neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(dists)]
        if not neighbours:
            return _floor_hour(t_i)
        j = min(neighbours, key=dists.__getitem__)
        d_i, d_j = dists[i], dists[j]
        t_j = self.lines[j][0]
        frac = d_i / (d_i + d_j) if d_i + d_j > 0 else 0.0
        return _floor_hour(t_i + (t_j - t_i) * frac)


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


class ReplaySource:
    """A storm replay on disk, queried by time."""

    is_replay = True

    def __init__(self, root: Path):
        self.root = Path(root)
        self.manifest = _load_json(str(self.root / "manifest.json"))
        self.id: str = self.manifest["id"]
        self.storm_id: str = self.manifest["storm_id"]
        self.name: str = self.manifest["name"]
        self.start = parse_time(self.manifest["start"])
        self.end = parse_time(self.manifest["end"])
        self.advisories = sorted(
            (
                Advisory(
                    adv=a["adv"], advisory_number=a["advisory_number"], issued_at=parse_time(a["issued_at"]),
                    intermediate=a["intermediate"], classification=a["classification"], category=a.get("category"),
                    lat=a["lat"], lon=a["lon"], max_wind_kt=a.get("max_wind_kt"), pressure_mb=a.get("pressure_mb"),
                    headline=a.get("headline"), file=a["file"], wsp=a.get("wsp"), toa=a.get("toa"),
                    products_from=a.get("products_from"),
                )
                for a in self.manifest["advisories"]
            ),
            key=lambda a: a.issued_at,
        )
        self._issued = [a.issued_at for a in self.advisories]

    # --- time queries -------------------------------------------------------------------------

    def advisory_at(self, now: datetime) -> Advisory | None:
        """The newest advisory issued at or before `now`; None before the first one or after the replay ends."""
        if now >= self.end:
            return None
        i = bisect_right(self._issued, now)
        return self.advisories[i - 1] if i else None

    def next_advisory_time(self, now: datetime) -> datetime | None:
        i = bisect_right(self._issued, now)
        return self._issued[i] if i < len(self._issued) else None

    def boundaries(self, after: datetime, until: datetime) -> list[datetime]:
        """Every moment in (after, until] where the replay's inputs can change: advisories and alert
        starts/ends for the demo ZIPs. The scheduler evaluates each one so a big clock jump still
        records events at the right times."""
        times = set(t for t in self._issued if after < t <= until)
        for z in self.manifest.get("demo_zips", []):
            for e in self._alert_events(z):
                for t in (parse_time(e["issued"]), parse_time(e["expires"])):
                    if after < t <= until:
                        times.add(t)
        if after < self.end <= until:
            times.add(self.end)
        return sorted(times)

    # --- point queries ------------------------------------------------------------------------

    def exposure(self, lat: float, lon: float, zip_code: str | None, now: datetime) -> Exposure:
        adv = self.advisory_at(now)
        alerts = self.alerts(zip_code, now)
        if adv is None:
            return Exposure(None, alerts=alerts)
        pt = Point(lon, lat)
        cone = self._cone(adv.file)
        in_cone = bool(cone is not None and cone.contains(pt))
        p34 = p64 = 0.0
        if adv.wsp:
            wsp = self._wsp(adv.wsp)
            p34, p64 = wsp.prob_at(lon, lat, "34"), wsp.prob_at(lon, lat, "64")
        eta, eta_source = None, None
        if adv.toa:
            eta = self._toa(adv.toa).eta_at(lon, lat, (adv.lon, adv.lat), now)
            eta_source = "toa_kmz" if eta else None
        elif p34 >= 0.05 or in_cone:
            eta = self._estimate_eta(adv, lon, lat)
            eta_source = "estimate" if eta else None
        return Exposure(adv, p34=p34, p64=p64, in_cone=in_cone, eta=eta, eta_source=eta_source, alerts=alerts)

    def alerts(self, zip_code: str | None, now: datetime) -> list[dict]:
        """Watches and warnings in force at `now` (issued <= now < expires). Only the replay's demo
        ZIPs have archived alerts; any other ZIP gets none."""
        return [e for e in self._alert_events(zip_code) if parse_time(e["issued"]) <= now < parse_time(e["expires"])]

    def storm_passed(self, lat: float, lon: float, now: datetime) -> bool:
        """The centre's closest approach to the point is behind us: it is moving away along the forecast."""
        adv = self.advisory_at(now)
        if adv is None:
            return False
        pts = self._forecast_points(adv.file)
        if len(pts) < 2:
            return False
        dists = [_km(p_lon, p_lat, lon, lat) for _, p_lon, p_lat, _ in pts]
        return dists[0] <= min(dists[1:])

    # --- map layers ---------------------------------------------------------------------------

    def cone_layer(self, now: datetime) -> dict:
        adv = self.advisory_at(now)
        if adv is None:
            return _fc([])
        feats = [f for f in self._features(adv.file) if f["properties"]["layer"] == "cone"]
        return _fc([{"type": "Feature", "geometry": f["geometry"], "properties": {
            "advisory": adv.advisory_number, "storm_id": self.storm_id, "name": self.name,
            "issued_at": iso(adv.issued_at)}} for f in feats])

    def track_layer(self, now: datetime) -> dict:
        adv = self.advisory_at(now)
        if adv is None:
            return _fc([])
        out = []
        for f in self._features(adv.file):
            p = f["properties"]
            if p["layer"] != "track":
                continue
            if p["kind"] == "forecast_line":
                props = {"kind": "line", "advisory": adv.advisory_number}
            else:
                kt = p.get("max_wind_kt")
                props = {
                    "kind": "point", "advisory": adv.advisory_number, "tau_h": p["tau_h"],
                    "valid_time": p["valid_time"], "intensity_kt": kt,
                    "max_wind_mph": round(kt * KT_TO_MPH) if kt is not None else None,
                    "category": p.get("category"), "storm_type": p.get("storm_type"), "label": p.get("label"),
                }
            out.append({"type": "Feature", "geometry": f["geometry"], "properties": props})
        return _fc(out)

    # --- file access (cached) -----------------------------------------------------------------

    def _path(self, rel: str) -> str:
        return str(self.root / rel)

    def _features(self, rel: str) -> list[dict]:
        return _load_json(self._path(rel))["features"]

    def _alert_events(self, zip_code: str | None) -> list[dict]:
        if not zip_code:
            return []
        path = self.root / "alerts" / f"{zip_code}.json"
        return _load_json(str(path))["events"] if path.exists() else []

    @cached_property
    def _cones(self) -> dict:
        return {}

    def _cone(self, rel: str):
        if rel not in self._cones:
            polys = [shape(f["geometry"]) for f in self._features(rel) if f["properties"]["layer"] == "cone"]
            self._cones[rel] = prepared.prep(polys[0].buffer(CONE_BUFFER_DEG)) if polys else None
        return self._cones[rel]

    def _wsp(self, rel: str) -> _Wsp:
        return _cached_wsp(self._path(rel))

    def _toa(self, rel: str) -> _Toa:
        return _cached_toa(self._path(rel))

    def _forecast_points(self, rel: str) -> list[tuple[int, float, float, datetime]]:
        pts = [
            (f["properties"]["tau_h"], *f["geometry"]["coordinates"][:2], parse_time(f["properties"]["valid_time"]))
            for f in self._features(rel)
            if f["properties"].get("kind") == "forecast_point"
        ]
        return sorted(pts)

    def _estimate_eta(self, adv: Advisory, lon: float, lat: float) -> datetime | None:
        """When the forecast centre first comes within ESTIMATE_RADIUS_KM, walking the track linearly."""
        pts = self._forecast_points(adv.file)
        for (_, lon_a, lat_a, t_a), (_, lon_b, lat_b, t_b) in zip(pts, pts[1:]):
            steps = max(1, int((t_b - t_a) / timedelta(hours=1)))
            for s in range(steps + 1):
                f = s / steps
                if _km(lon_a + (lon_b - lon_a) * f, lat_a + (lat_b - lat_a) * f, lon, lat) <= ESTIMATE_RADIUS_KM:
                    return _floor_hour(t_a + (t_b - t_a) * f)
        return None


@lru_cache(maxsize=64)
def _cached_wsp(path: str) -> _Wsp:
    return _Wsp(_load_json(path))


@lru_cache(maxsize=64)
def _cached_toa(path: str) -> _Toa:
    return _Toa(_load_json(path))


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def empty_fc() -> dict:
    return _fc([])


# --- catalogue of replays on disk ------------------------------------------------------------


@lru_cache(maxsize=8)
def _replay(root: str) -> ReplaySource:
    return ReplaySource(Path(root))


def load_replay(replay_dir: Path, storm: str) -> ReplaySource | None:
    root = Path(replay_dir) / storm
    if not (root / "manifest.json").exists():
        return None
    return _replay(str(root))


def list_replays(replay_dir: Path) -> list[dict]:
    """GET /demo/storms rows."""
    out = []
    for manifest in sorted(Path(replay_dir).glob("*/manifest.json")):
        m = _load_json(str(manifest))
        out.append({
            "id": m["id"], "name": m["name"], "year": m["year"], "landfall_at": m.get("landfall_at"),
            "description": m.get("description", ""), "demo_zips": m.get("demo_zips", []),
            "start": m["start"], "end": m["end"], "advisories": len(m["advisories"]),
        })
    return out
