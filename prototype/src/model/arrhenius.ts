// Spoilage kinetics.
//   k(T) = k_ref · exp( (Ea/R) · (1/T_ref − 1/T) ) · f_RH
//   Q(t) = exp( −∫ k dt )                      first-order quality loss, Q0 = 1 at harvest
// k_ref is calibrated so Q falls from 1 to Q_MIN over the crop's sourced shelf life at its reference temperature.
// Ea is derived from Q10 (FAO AGS Bulletin 152: rate rises 2–3× per +10 °C) around 20 °C.
// Sellable fraction uses the lognormal unit-to-unit spread from backend/app/domain/decay.py (σ = 0.25, A17).
import type { Crop } from "../data/crops";

export const R_GAS = 8.314;
export const Q_MIN = 0.6;
export const SIGMA = 0.25;
const K0 = 273.15;

export function eaFromQ10(q10: number, aroundC = 20): number {
  const t1 = aroundC + K0, t2 = aroundC + 10 + K0;
  return (Math.log(q10) * R_GAS * t1 * t2) / 10;
}

export function kRef(crop: Crop): number {
  return -Math.log(Q_MIN) / crop.refLifeH;
}

export function humidityFactor(crop: Crop, rh: number): number {
  const wet = Math.max(0, rh - crop.rhOpt) / 100;
  const dry = Math.max(0, crop.rhOpt - rh) / 100;
  return 1 + crop.rotAlpha * wet + crop.dryBeta * dry;
}

/** Rate constant (per hour) at cargo temperature tC (°C) and relative humidity rh (%). */
export function rate(crop: Crop, tC: number, rh: number, ea: number): number {
  const T = Math.min(55, Math.max(-2, tC)) + K0;
  const Tref = crop.refTempC + K0;
  return kRef(crop) * Math.exp((ea / R_GAS) * (1 / Tref - 1 / T)) * humidityFactor(crop, rh);
}

// Abramowitz–Stegun normal CDF.
export function phi(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp((-x * x) / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}

/**
 * Fraction of units still sellable at quality q. `tolerance` > 1 for buyers that accept older
 * produce (processors). `km` adds handling damage.
 */
export function sellableFraction(crop: Crop, q: number, km = 0, tolerance = 1): number {
  if (q <= 0) return 0;
  const ageRatio = Math.log(q) / Math.log(Q_MIN); // equivalent age / reference life
  if (ageRatio <= 0) return 1 - crop.handlingPer100km * km / 100;
  const spoiled = phi(Math.log(ageRatio / tolerance) / SIGMA);
  return Math.max(0, (1 - spoiled) * (1 - crop.handlingPer100km * km / 100));
}

/** Quality left after `hours` at a constant rate. */
export function decay(q: number, k: number, hours: number): number {
  return q * Math.exp(-k * hours);
}
