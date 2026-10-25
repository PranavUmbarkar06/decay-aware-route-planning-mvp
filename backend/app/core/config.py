"""Typed, fail-fast config. Unknown keys raise (extra='forbid')."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "config"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- config.yaml
class Runtime(_Strict):
    demo_mode: bool
    database_url: str
    timezone_display: str
    cors_origins: list[str]
    demo_clock_utc: str | None = None


class Auth(_Strict):
    mode: Literal["dev_stub", "provider"]
    otp_ttl_s: int = Field(gt=0)
    otp_max_attempts: int = Field(gt=0)
    otp_requests_per_min: int = Field(5, gt=0)
    jwt_ttl_s: int = Field(gt=0)
    jwt_secret_env: str


class Pin(_Strict):
    digits: int = Field(ge=4, le=8)
    max_failures: int = Field(gt=0)
    lockout_s: int = Field(gt=0)
    ttl_h: int = Field(gt=0)
    rate_limit_per_min: int = Field(gt=0)


class Handover(_Strict):
    weight_tolerance_pct: float = Field(ge=0)


class Wastage(_Strict):
    undo_window_s: int = Field(gt=0)


class Rescue(_Strict):
    claim_timer_s: int = Field(gt=0)
    offer_ttl_s: int = Field(gt=0)
    safety_margin_frac: float = Field(gt=0, le=1)
    max_road_time_h: float = Field(gt=0)
    wave_size: int = Field(gt=0)


class Matching(_Strict):
    weights: dict[str, float]

    @model_validator(mode="after")
    def _keys(self) -> Matching:
        if set(self.weights) != {"road_time", "life_margin", "capacity_fit"}:
            raise ValueError("matching.weights must have exactly road_time, life_margin, capacity_fit")
        return self


class CrowdMeter(_Strict):
    trailing_days: int = Field(gt=0)
    warn_ratio: float = Field(gt=1)
    stale_after_days: int = Field(gt=0)
    alternate_radius_h: float = Field(gt=0)


class MapCfg(_Strict):
    tile_url: str
    attribution: str


class Features(_Strict):
    ml_surrogate: bool
    push_notifications: bool


class Units(_Strict):
    internal: Literal["kg"]
    display_options: list[str]


class AppConfig(_Strict):
    product_name: str
    logo_path: str
    version: str
    runtime: Runtime
    auth: Auth
    pin: Pin
    handover: Handover
    wastage: Wastage
    rescue: Rescue
    matching: Matching
    crowd_meter: CrowdMeter
    map: MapCfg
    features: Features
    units: Units


# ---------------------------------------------------------------- commodities.yaml
class SourcedValue(_Strict):
    value: float | None
    status: Literal["SOURCED", "ASSUMPTION", "MISSING"]
    source: str | None = None
    rationale: str | None = None
    ref_temp_c: float | None = None
    note: str | None = None
    source_detail: str | None = None


class CommodityCfg(_Strict):
    label: str
    agmarknet_cmdt_id: int
    base_shelf_life_h: SourcedValue
    handling_damage_per_100km: SourcedValue
    nabcons_market_level_loss_pct: SourcedValue


class Q10Cfg(_Strict):
    range: tuple[float, float]
    default: float
    status: Literal["SOURCED", "ASSUMPTION", "MISSING"]
    source: str
    note: str | None = None


class MissingPlaceholder(_Strict):
    base_shelf_life_h: float
    ref_temp_c: float
    status: Literal["ASSUMPTION"]
    warning: str


class TemperatureModelCfg(_Strict):
    mode: Literal["fao_table1", "q10"]
    table_csv: str
    status: Literal["SOURCED", "ASSUMPTION", "MISSING"]
    source: str
    clamp_c: tuple[float, float]
    note: str | None = None


class CommoditiesConfig(_Strict):
    temperature_model: TemperatureModelCfg
    q10: Q10Cfg
    commodities: dict[str, CommodityCfg]
    missing_placeholder: MissingPlaceholder


# ---------------------------------------------------------------- thresholds / speeds / geography
class TrafficLight(_Strict):
    provenance: Literal["ASSUMPTION"]
    needs_confirmation_with_operators: bool
    red_below_h: float
    green_at_or_above_h: float

    @model_validator(mode="after")
    def _order(self) -> TrafficLight:
        if not self.red_below_h < self.green_at_or_above_h:
            raise ValueError("red_below_h must be < green_at_or_above_h (no gaps, no overlap)")
        return self


class GraphThresholds(_Strict):
    snap_distance_review_m: float
    geocode_confidence_min: float


class QualityThresholds(_Strict):
    saleable_min: float
    processing_min: float


class Thresholds(_Strict):
    traffic_light: TrafficLight
    graph: GraphThresholds
    quality: QualityThresholds


class AccessLeg(_Strict):
    detour_factor: float
    speed_kmh: float


class Speeds(_Strict):
    provenance: Literal["ASSUMPTION"]
    needs_validation: bool
    truck_speed_cap_kmh: float
    plausible_range_kmh: tuple[float, float]
    class_default_kmh: dict[str, float]
    access_leg: AccessLeg


class District(_Strict):
    name: str
    agmarknet: str
    osm_query: str


class Geography(_Strict):
    label: str
    state: str
    agmarknet_state_id: int
    districts: list[District]
    road_classes: list[str]
    boundary_buffer_km: float
    illustrative_markets_not_supported: list[str] = []


class GeographyConfig(_Strict):
    active: str
    geographies: dict[str, Geography]

    @property
    def current(self) -> Geography:
        return self.geographies[self.active]


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def app_config() -> AppConfig:
    return AppConfig.model_validate(_load("config.yaml"))


@lru_cache
def commodities_config() -> CommoditiesConfig:
    return CommoditiesConfig.model_validate(_load("commodities.yaml"))


@lru_cache
def thresholds() -> Thresholds:
    return Thresholds.model_validate(_load("thresholds.yaml"))


@lru_cache
def speeds() -> Speeds:
    return Speeds.model_validate(_load("speeds.yaml"))


@lru_cache
def geography() -> GeographyConfig:
    return GeographyConfig.model_validate(_load("geography.yaml"))
