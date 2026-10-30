// Demo consignments and buyers. Coordinates from data/processed/geo/nodes.geojson (Kamptee/Kalamna corrected by hand).
// Prices ₹/kg = median Agmarknet modal price (inputs/*.csv, Nov 2025 – Oct 2026) / 100; "indicative" where no
// Agmarknet row exists for that market. Processor prices and tolerances are ASSUMPTIONS.
import type { CropId } from "./crops";

export interface Buyer {
  id: string;
  name: string;
  short: string;
  lon: number;
  lat: number;
  kind: "mandi" | "processor";
}

export const BUYERS: Record<string, Buyer> = {
  nagpur: { id: "nagpur", name: "APMC Nagpur (Kalamna)", short: "Nagpur", lon: 79.1300, lat: 21.1650, kind: "mandi" },
  kamptee: { id: "kamptee", name: "APMC Kamthi", short: "Kamthi", lon: 79.1964, lat: 21.2171, kind: "mandi" },
  hingna: { id: "hingna", name: "APMC Hingna", short: "Hingna", lon: 78.9684, lat: 21.0752, kind: "mandi" },
  kalmeshwar: { id: "kalmeshwar", name: "APMC Kalmeshwar", short: "Kalmeshwar", lon: 78.9082, lat: 21.2374, kind: "mandi" },
  wardha: { id: "wardha", name: "APMC Wardha", short: "Wardha", lon: 78.6017, lat: 20.7407, kind: "mandi" },
  hinganghat: { id: "hinganghat", name: "APMC Hinganghat", short: "Hinganghat", lon: 78.8325, lat: 20.5338, kind: "mandi" },
  chandrapur: { id: "chandrapur", name: "APMC Chandrapur", short: "Chandrapur", lon: 79.2987, lat: 19.9508, kind: "mandi" },
  narkhed: { id: "narkhed", name: "APMC Narkhed", short: "Narkhed", lon: 78.5337, lat: 21.4713, kind: "mandi" },
  bhandara: { id: "bhandara", name: "APMC Bhandara", short: "Bhandara", lon: 79.6661, lat: 21.1549, kind: "mandi" },
  butibori: { id: "butibori", name: "Butibori MIDC food processor", short: "Butibori proc.", lon: 78.9500, lat: 20.9300, kind: "processor" },
  adm: { id: "adm", name: "ADM Agro Industries (juice)", short: "ADM juice", lon: 79.2307, lat: 21.3165, kind: "processor" },
  paras: { id: "paras", name: "Paras Agro Industries", short: "Paras proc.", lon: 78.9752, lat: 20.2312, kind: "processor" },
};

export interface Offer { buyer: string; priceKg: number; indicative?: boolean; tolerance?: number }

export interface Consignment {
  id: string;
  label: string;
  crop: CropId;
  kg: number;
  origin: { name: string; lon: number; lat: number };
  q0: number;          // quality at dispatch (after harvest + farm-gate holding)
  harvestNote: string;
  offers: Offer[];
}

export const CONSIGNMENTS: Consignment[] = [
  {
    id: "T1", label: "Truck 1 · Tomato", crop: "tomato", kg: 8000,
    origin: { name: "Sindi (Selu), Wardha", lon: 78.887, lat: 20.8046 },
    q0: 0.74, harvestNote: "picked ~3 days ago, firm-ripe",
    offers: [
      { buyer: "nagpur", priceKg: 23.0 },
      { buyer: "kamptee", priceKg: 23.1 },
      { buyer: "hingna", priceKg: 21.3 },
      { buyer: "kalmeshwar", priceKg: 18.2 },
      { buyer: "wardha", priceKg: 17.0, indicative: true },
      { buyer: "hinganghat", priceKg: 16.0, indicative: true },
      { buyer: "butibori", priceKg: 11.0, indicative: true, tolerance: 1.6 },
    ],
  },
  {
    id: "T2", label: "Truck 2 · Orange", crop: "orange", kg: 10000,
    origin: { name: "Katol orchards", lon: 78.5866, lat: 21.2752 },
    q0: 0.70, harvestNote: "picked ~5 weeks into ambient holding",
    offers: [
      { buyer: "nagpur", priceKg: 38.3 },
      { buyer: "kamptee", priceKg: 43.1 },
      { buyer: "hingna", priceKg: 23.0 },
      { buyer: "narkhed", priceKg: 38.0 },
      { buyer: "bhandara", priceKg: 36.0, indicative: true },
      { buyer: "adm", priceKg: 18.0, indicative: true, tolerance: 1.6 },
    ],
  },
  {
    id: "T3", label: "Truck 3 · Onion", crop: "onion", kg: 12000,
    origin: { name: "Warora, Chandrapur", lon: 79.0028, lat: 20.2343 },
    q0: 0.72, harvestNote: "kharif onion, ~4 months curing",
    offers: [
      { buyer: "nagpur", priceKg: 18.8 },
      { buyer: "kamptee", priceKg: 22.9 },
      { buyer: "hingna", priceKg: 19.3 },
      { buyer: "chandrapur", priceKg: 21.5 },
      { buyer: "wardha", priceKg: 18.0, indicative: true },
      { buyer: "hinganghat", priceKg: 17.0, indicative: true },
      { buyer: "paras", priceKg: 9.0, indicative: true, tolerance: 1.6 },
    ],
  },
];

// Operating cost assumptions (₹). Diesel ₹90/L at ~3 km/L laden; driver + truck rent ~₹600/h.
export const COST = { perHour: 600, perKm: 30, co2PerKm: 0.9, reeferCapex: 2500000, reeferPerHour: 250 };
