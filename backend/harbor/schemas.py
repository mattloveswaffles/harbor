"""API request and response models. These match docs/API.md field for field and feed docs/openapi.json."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

RiskLevel = Literal["clear", "monitor", "prepare", "act", "shelter", "recover"]
Mobility = Literal["none", "walker", "wheelchair"]
HomeType = Literal["site_built", "mobile"]
EvacZone = Literal["A", "B", "C", "D", "E", "none", "unsure"]
ZipCode = Field(pattern=r"^\d{5}$", examples=["33602"])
ChildAge = Annotated[int, Field(ge=0, le=17)]


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Pet(BaseModel):
    type: str = Field(min_length=1, max_length=30, examples=["dog"])
    count: int = Field(1, ge=1, le=20)


class Medical(BaseModel):
    power_dependent_device: bool = False
    oxygen: bool = False
    dialysis: bool = False
    refrigerated_meds: bool = False


class HouseholdModel(BaseModel):
    adults: int = Field(1, ge=0, le=20, description="Adults under 65; seniors are counted separately")
    children_ages: list[ChildAge] = Field(default_factory=list, max_length=20)
    seniors: int = Field(0, ge=0, le=20)
    pets: list[Pet] = Field(default_factory=list, max_length=10)
    mobility: Mobility = "none"
    medical: Medical = Field(default_factory=Medical)
    has_car: bool = True
    home_type: HomeType = "site_built"
    evac_zone: EvacZone = "unsure"

    @model_validator(mode="after")
    def someone_grown_up(self):
        if self.adults + self.seniors < 1:
            raise ValueError("a household needs at least one adult or senior")
        return self


class HouseholdPatch(BaseModel):
    """Send only the fields that change."""

    adults: int | None = Field(None, ge=0, le=20)
    children_ages: list[ChildAge] | None = Field(None, max_length=20)
    seniors: int | None = Field(None, ge=0, le=20)
    pets: list[Pet] | None = Field(None, max_length=10)
    mobility: Mobility | None = None
    medical: Medical | None = None
    has_car: bool | None = None
    home_type: HomeType | None = None
    evac_zone: EvacZone | None = None


class UserSettings(BaseModel):
    auto_approve: bool = False
    max_etf_sell_cents: int = Field(300000, ge=0)
    cancel_window_minutes: int = Field(120, ge=1, le=1440)
    rebuy_opt_in: bool = False


class SettingsPatch(BaseModel):
    auto_approve: bool | None = None
    max_etf_sell_cents: int | None = Field(None, ge=0)
    cancel_window_minutes: int | None = Field(None, ge=1, le=1440)
    rebuy_opt_in: bool | None = None


class UserOut(BaseModel):
    id: str
    name: str
    zip: str
    location: Location
    location_source: Literal["zcta", "gps"]
    household: HouseholdModel
    settings: UserSettings
    nessie_customer_id: str | None
    risk_level: RiskLevel


class CreateUser(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    zip: str = ZipCode
    location: Location | None = None
    household: HouseholdModel | None = None


class UserPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    zip: str | None = Field(None, pattern=r"^\d{5}$")
    location: Location | None = None
    settings: SettingsPatch | None = None


class AccountOut(BaseModel):
    id: str
    nessie_id: str | None
    type: Literal["checking", "savings", "brokerage_cash"]
    nessie_type: str
    nickname: str
    balance_cents: int
    balance_synced_at: str | None = Field(description="ISO 8601 UTC time of the last Nessie read")


class ZipOut(BaseModel):
    zip: str
    city: str
    state: str
    lat: float
    lon: float


class PersonaIn(BaseModel):
    persona: Literal["maria", "ruth"] = "maria"


class ClockOut(BaseModel):
    running: bool
    storm: str | None
    now: str
    speed: float
    paused_reason: str | None


class ResetOut(BaseModel):
    ok: bool
    server_time: str
    users_reset: int
    clock: ClockOut


class HealthOut(BaseModel):
    ok: bool
    mode: Literal["demo", "live"]
    nessie: Literal["ok", "degraded", "fake", "missing_key"]
    nhc: str
    ai: Literal["ok", "off"]
    clock: str


# --- Storm, map and demo (H8-14) -------------------------------------------------------------

AlertType = Literal[
    "hurricane_watch", "hurricane_warning", "tropical_storm_watch", "tropical_storm_warning",
    "storm_surge_watch", "storm_surge_warning", "extreme_wind_warning",
]


class Position(BaseModel):
    lat: float
    lon: float


class StormOut(BaseModel):
    id: str = Field(examples=["al142024"])
    name: str
    classification: str = Field(description="hurricane, tropical_storm, tropical_depression, post_tropical, ...")
    category: int | None = Field(description="Saffir-Simpson category; null below hurricane strength")
    advisory_number: str = Field(examples=["15", "15A"])
    advisory_time: str
    next_advisory_time: str | None
    is_replay: bool
    headline: str | None = Field(description="The public advisory's summary line, as NHC wrote it")
    position: Position
    max_wind_mph: int | None


class AlertOut(BaseModel):
    type: AlertType
    headline: str
    issued: str
    expires: str
    source: Literal["nws", "iem"]


class ZipExposureOut(BaseModel):
    ts_wind_probability_5day: float = Field(description="0..1, chance of tropical-storm winds within 5 days")
    hurricane_wind_probability_5day: float = Field(description="0..1, chance of hurricane winds within 5 days")
    in_forecast_cone: bool
    earliest_ts_winds_eta: str | None
    eta_source: Literal["toa_kmz", "pws_text", "estimate"] | None
    alerts: list[AlertOut]


class StormStatusOut(BaseModel):
    server_time: str
    risk_level: RiskLevel
    risk_reason: str
    storm: StormOut | None
    at_your_zip: ZipExposureOut


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[dict] = Field(default_factory=list)


class MapLayers(BaseModel):
    home: FeatureCollection
    cone: FeatureCollection
    track: FeatureCollection
    route: FeatureCollection
    destinations: FeatureCollection
    shelters: FeatureCollection
    lodging: FeatureCollection
    atms: FeatureCollection
    sensors: FeatureCollection


class MapOut(BaseModel):
    server_time: str
    layers: MapLayers
    attribution: list[str]


class DemoStormOut(BaseModel):
    id: str = Field(examples=["milton-2024"])
    name: str
    year: int
    landfall_at: str | None
    description: str
    demo_zips: list[str]
    start: str = Field(description="Where /demo/start puts the clock")
    end: str = Field(description="The replay has no storm after this time")
    advisories: int


class DemoStartIn(BaseModel):
    storm: str = Field("milton-2024", examples=["milton-2024"])
    speed: float | None = Field(None, gt=0, le=86400, description="Storm seconds per real second; default 1800")


class DemoAdvanceIn(BaseModel):
    """Send exactly one of `hours`, `to` or `to_risk`."""

    hours: float | None = Field(None, gt=0, le=240)
    to: Literal["next_advisory"] | None = None
    to_risk: RiskLevel | None = None


# --- Activity feed and AI (H36-40) -----------------------------------------------------------

class EventOut(BaseModel):
    id: str
    at: str
    type: str
    message: str
    data: dict


RiskKind = Literal["liquidity", "tax", "settlement", "gouging", "availability", "medical", "other"]
ReviewSource = Literal["checking", "savings", "etf_sale"]
ExplainCategory = Literal["plan_explanation", "general_education", "personal_advice_request", "off_topic"]


class ReviewSourceOut(BaseModel):
    source: ReviewSource
    move_id: str | None
    amount_cents: int
    reasoning: str


class ReviewAlternativeOut(BaseModel):
    alt_id: str
    why_consider: str
    tradeoff: str


class ReviewRiskOut(BaseModel):
    kind: RiskKind
    text: str


class HouseholdNoteOut(BaseModel):
    need: str
    advice: str
    source_url: str


class LodgingCommentOut(BaseModel):
    lodging_id: str
    comment: str


class PlanReviewOut(BaseModel):
    server_time: str
    plan_id: str
    plan_version: int
    label: str
    summary: str
    per_source: list[ReviewSourceOut]
    alternatives: list[ReviewAlternativeOut]
    risks: list[ReviewRiskOut]
    double_check: list[str]
    household_notes: list[HouseholdNoteOut]
    lodging_comments: list[LodgingCommentOut]
    generated_by: str = Field(description="The model id, or `template`")
    validated: bool


class ExplainIn(BaseModel):
    question: str = Field(min_length=1, max_length=500, examples=["Why sell TBUX and not TCAF?"])
    move_id: str | None = None


class AiInfo(BaseModel):
    source: Literal["claude", "template"]
    model: str | None
    validated: bool


class ExplainOut(BaseModel):
    server_time: str
    category: ExplainCategory
    answer: str
    ai: AiInfo
    suggested_questions: list[str]


class DemoAiIn(BaseModel):
    enabled: bool


class DemoAiOut(BaseModel):
    enabled: bool = Field(description="The toggle as set")
    ai: Literal["ok", "off"] = Field(description="`ok` only when the toggle is on and ANTHROPIC_API_KEY is set")
