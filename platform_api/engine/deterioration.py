"""Crop deterioration model (plan v2 §6). Deterministic and transparent.

Mechanisms are kept separate so nothing is counted twice:
  1. Physiological decay: ONE time integral of an Arrhenius rate with a humidity factor.
         k(T, RH) = k_ref · exp(Ea/R · (1/T_ref − 1/T)) · f_RH
         Q(t)     = Q0 · exp(−∫ k dt)
     Pre-dispatch exposure, transit and market waiting are all just time inside this integral.
  2. Mechanical damage from vibration/compression: D_mech = 1 − exp(−β_crop · pack · load · Σ (r/10)² · km)
  3. Handling damage: D_hand = 1 − (1 − h_crop)^events
  4. Grading of surviving units by the lognormal unit-to-unit spread (σ, assumption A17):
         a = ln Q / ln Q_min                       (equivalent age as a fraction of reference life)
         rejected   = Φ(ln(a)/σ)                   (past Q_min)
         downgraded = Φ(ln(a/g)/σ) − rejected      (past grade ratio g)
         grade A    = 1 − Φ(ln(a/g)/σ)
     Survival fractions multiply: physically lost units are removed before grading.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .crops import Common, CropProfile, load

R_GAS = 8.314
K0 = 273.15


def ea_from_q10(q10: float, around_c: float = 20.0) -> float:
    t1, t2 = around_c + K0, around_c + 10 + K0
    return math.log(q10) * R_GAS * t1 * t2 / 10


def k_ref(crop: CropProfile, q_min: float) -> float:
    return -math.log(q_min) / crop.ref_life_h


def humidity_factor(crop: CropProfile, rh: float) -> float:
    wet = max(0.0, rh - crop.rh_opt) / 100
    dry = max(0.0, crop.rh_opt - rh) / 100
    return 1 + crop.rot_alpha * wet + crop.dry_beta * dry


def rate(crop: CropProfile, common: Common, temp_c: float, rh: float, q10: float | None = None) -> float:
    ea = ea_from_q10(q10 or common.q10)
    T = min(55.0, max(-2.0, temp_c)) + K0
    t_ref = crop.ref_temp_c + K0
    return k_ref(crop, common.q_min) * math.exp(ea / R_GAS * (1 / t_ref - 1 / T)) * humidity_factor(crop, rh)


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def grade_split(q: float, common: Common) -> tuple[float, float, float]:
    """(grade A, downgraded, rejected) fractions of surviving units at quality q."""
    if q >= 1:
        return 1.0, 0.0, 0.0
    if q <= 0:
        return 0.0, 0.0, 1.0
    a = math.log(q) / math.log(common.q_min)
    s = common.sigma
    rejected = phi(math.log(a) / s)
    past_grade = phi(math.log(a / common.grade_ratio) / s)
    return 1 - past_grade, past_grade - rejected, rejected


@dataclass
class Segment:
    """One stretch of road (or a stationary period when km == 0)."""
    hours: float
    km: float = 0.0
    ambient_c: float = 30.0
    rh: float = 60.0
    roughness: float = 0.0     # 0 (smooth expressway) … 10 (very poor)
    traffic: float = 0.0       # 0–10, adds idling heat
    moving: bool = True


@dataclass
class ShipmentSpec:
    crop: str
    kg: float
    condition: str | None = None
    packaging: str | None = None
    loading: str = "proper"
    vehicle: str | None = None
    refrigeration_ok: bool = True
    reefer_fail_at_h: float | None = None
    handling_events: int = 2
    pre_dispatch_h: float = 0.0
    market_wait_h: float = 0.0
    dispatch_hour: float = 6.0
    price_rs_kg: float | None = None
    q10: float | None = None
    breakdown_h: float = 0.0


@dataclass
class Outcome:
    kg: float
    q_arrival: float
    physical_loss_kg: float
    rejected_kg: float
    downgraded_kg: float
    grade_a_kg: float
    saleable_kg: float
    wastage_kg: float
    revenue_rs: float
    hours: float
    km: float
    vib_dose: float
    mean_cargo_temp_c: float
    max_cargo_temp_c: float
    d_mech: float
    d_hand: float
    heat_degree_h: float = 0.0     # °C·h of cargo temperature above the crop's ideal (reefer set point)
    profile: list[tuple[float, float]] = field(default_factory=list)   # (hour, quality)

    @property
    def wastage_pct(self) -> float:
        return 100 * self.wastage_kg / self.kg if self.kg else 0.0


def cargo_temperature(spec: ShipmentSpec, crop: CropProfile, common: Common, seg: Segment, t_h: float) -> float:
    """Cargo temperature at elapsed time t_h for this segment's ambient conditions."""
    veh = common.vehicles[spec.vehicle or crop.default_vehicle]
    hour = (spec.dispatch_hour + t_h) % 24
    sun = common.solar_load_c if 9 <= hour < 17 else 0.0
    passive = seg.ambient_c + sun + common.idle_heat_per_traffic_c * seg.traffic
    if not veh["refrigerated"]:
        return passive
    if spec.refrigeration_ok and spec.reefer_fail_at_h is None:
        return crop.reefer_set_c
    fail_at = 0.0 if not spec.refrigeration_ok else spec.reefer_fail_at_h
    if t_h < fail_at:
        return crop.reefer_set_c
    w = 1 - math.exp(-(t_h - fail_at) / common.reefer_failure_tau_h)
    return crop.reefer_set_c + (passive - crop.reefer_set_c) * w


def cargo_rh(spec: ShipmentSpec, crop: CropProfile, common: Common, seg: Segment) -> float:
    veh = common.vehicles[spec.vehicle or crop.default_vehicle]
    if veh["refrigerated"] and spec.refrigeration_ok and spec.reefer_fail_at_h is None:
        return crop.rh_opt
    return min(100.0, seg.rh + (1 - veh["ventilation"]) * common.closed_body_rh_rise)


@dataclass
class StartState:
    """Mid-trip state, so a truck already on the road can be re-evaluated from where it is."""
    t_h: float = 0.0
    neg_ln_q: float | None = None
    km: float = 0.0
    dose: float = 0.0


def initial_quality(spec: ShipmentSpec) -> float:
    _, crops = load()
    crop = crops[spec.crop]
    return crop.initial_quality[spec.condition or crop.default_condition]


def simulate(spec: ShipmentSpec, route: list[Segment], *, sub_h: float = 0.5, start: StartState | None = None,
             include_pre: bool = True, include_wait: bool = True) -> Outcome:
    """Run a shipment over a list of segments. Pre-dispatch exposure and market wait are added as stationary time."""
    common, crops = load()
    crop = crops[spec.crop]
    q0 = crop.initial_quality[spec.condition or crop.default_condition]
    first = route[0] if route else Segment(hours=0)
    last = route[-1] if route else first
    segs: list[Segment] = []
    if include_pre and spec.pre_dispatch_h > 0 and not start:
        segs.append(Segment(hours=spec.pre_dispatch_h, ambient_c=first.ambient_c, rh=first.rh, moving=False))
    segs.extend(route)
    if spec.breakdown_h > 0 and not start:
        mid = route[len(route) // 2] if route else first
        segs.insert(len(segs) // 2 + 1, Segment(hours=spec.breakdown_h, ambient_c=mid.ambient_c, rh=mid.rh, traffic=0, moving=False))
    if include_wait and spec.market_wait_h > 0:
        segs.append(Segment(hours=spec.market_wait_h, ambient_c=last.ambient_c, rh=last.rh, moving=False))

    cond_key = spec.condition or crop.default_condition
    life_f = crop.condition_life_factor.get(cond_key, 1.0)
    st = start or StartState()
    neg_ln_q = st.neg_ln_q if st.neg_ln_q is not None else -math.log(q0)
    t = st.t_h
    km = st.km
    dose = st.dose
    temp_sum = 0.0
    temp_max = -99.0
    t_start = t
    heat_dh = 0.0
    profile = [(t, math.exp(-neg_ln_q))]
    for seg in segs:
        # integrate in sub-steps so time-of-day and reefer failure are resolved
        n = max(1, math.ceil(seg.hours / sub_h))
        dt = seg.hours / n
        for _ in range(n):
            tc = cargo_temperature(spec, crop, common, seg, t + dt / 2)
            rh = cargo_rh(spec, crop, common, seg)
            neg_ln_q += rate(crop, common, tc, rh, spec.q10) / life_f * dt
            temp_sum += tc * dt
            temp_max = max(temp_max, tc)
            heat_dh += max(0.0, tc - crop.reefer_set_c) * dt
            t += dt
        if seg.moving and seg.km > 0:
            km += seg.km
            dose += (seg.roughness / 10) ** 2 * seg.km
        profile.append((t, math.exp(-neg_ln_q)))

    pack = common.packaging_factor[spec.packaging or crop.default_packaging]
    loadf = common.loading_factor[spec.loading]
    d_mech = 1 - math.exp(-crop.beta_vib * pack * loadf * dose)
    d_hand = 1 - (1 - crop.handling_loss * pack) ** spec.handling_events
    survive = (1 - d_mech) * (1 - d_hand)

    q = math.exp(-neg_ln_q)
    a, d, r = grade_split(q, common)
    kg = spec.kg
    phys = kg * (1 - survive)
    surv_kg = kg * survive
    price = spec.price_rs_kg if spec.price_rs_kg is not None else crop.default_price
    grade_a, down, rej = surv_kg * a, surv_kg * d, surv_kg * r
    return Outcome(
        kg=kg, q_arrival=q, physical_loss_kg=phys, rejected_kg=rej, downgraded_kg=down, grade_a_kg=grade_a,
        saleable_kg=grade_a + down, wastage_kg=phys + rej,
        revenue_rs=grade_a * price + down * price * common.downgrade_price_factor,
        hours=t, km=km, vib_dose=dose, mean_cargo_temp_c=temp_sum / (t - t_start) if t > t_start else 0.0,
        max_cargo_temp_c=temp_max,
        d_mech=d_mech, d_hand=d_hand, heat_degree_h=heat_dh, profile=profile,
    )
