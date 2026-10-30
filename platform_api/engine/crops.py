"""Crop sensitivity profiles loaded from config/crops_v2.yaml. Crops differ only through these numbers."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "crops_v2.yaml"


def _v(x: Any) -> Any:
    return x["value"] if isinstance(x, dict) and "value" in x else x


@dataclass(frozen=True)
class CropProfile:
    id: str
    label: str
    ref_life_h: float
    ref_temp_c: float
    rh_opt: float
    rot_alpha: float
    dry_beta: float
    beta_vib: float
    handling_loss: float
    reefer_set_c: float
    default_price: float
    initial_quality: dict[str, float]
    condition_life_factor: dict[str, float]
    default_condition: str
    default_packaging: str
    default_vehicle: str
    packaging_note: str
    default_corridor: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class Common:
    q10: float
    q_min: float
    grade_ratio: float
    downgrade_price_factor: float
    sigma: float
    closed_body_rh_rise: float
    solar_load_c: float
    idle_heat_per_traffic_c: float
    reefer_failure_tau_h: float
    packaging_factor: dict[str, float]
    loading_factor: dict[str, float]
    vehicles: dict[str, dict[str, Any]]


@lru_cache(maxsize=1)
def load() -> tuple[Common, dict[str, CropProfile]]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    c = cfg["common"]
    common = Common(
        q10=_v(c["q10"]), q_min=_v(c["q_min"]), grade_ratio=_v(c["grade_ratio"]),
        downgrade_price_factor=_v(c["downgrade_price_factor"]), sigma=_v(c["sigma_unit_spread"]),
        closed_body_rh_rise=_v(c["closed_body_rh_rise"]), solar_load_c=_v(c["solar_load_c"]),
        idle_heat_per_traffic_c=_v(c["idle_heat_per_traffic_c"]), reefer_failure_tau_h=_v(c["reefer_failure_tau_h"]),
        packaging_factor=cfg["packaging_factor"], loading_factor=cfg["loading_factor"], vehicles=cfg["vehicles"],
    )
    crops = {}
    for cid, p in cfg["crops"].items():
        crops[cid] = CropProfile(
            id=cid, label=p["label"], ref_life_h=_v(p["ref_life_h"]), ref_temp_c=p["ref_temp_c"],
            rh_opt=_v(p["rh_opt"]), rot_alpha=_v(p["rot_alpha"]), dry_beta=_v(p["dry_beta"]),
            beta_vib=_v(p["beta_vib"]), handling_loss=_v(p["handling_loss"]), reefer_set_c=p["reefer_set_c"],
            default_price=_v(p["default_price_rs_kg"]), initial_quality=p["initial_quality"],
            condition_life_factor=p.get("condition_life_factor", {}),
            default_condition=p["default_condition"], default_packaging=p["default_packaging"],
            default_vehicle=p["default_vehicle"], packaging_note=p["packaging_note"],
            default_corridor=p["default_corridor"], raw=p,
        )
    return common, crops


def raw_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
