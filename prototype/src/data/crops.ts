// Crop constants. Shelf lives and handling damage ported from config/commodities.yaml (sources cited there).
// RH optimum from USDA HB66 storage guidance; humidity sensitivity (rotAlpha/dryBeta) is an ASSUMPTION.
export type CropId = "tomato" | "orange" | "onion";

export interface Crop {
  id: CropId;
  label: string;
  hi: string;
  mr: string;
  refLifeH: number;      // hours to reach Q_MIN at refTempC (SOURCED)
  refTempC: number;
  rhOpt: number;         // % RH optimum (HB66)
  rotAlpha: number;      // extra rot per +100 % RH above optimum (ASSUMPTION)
  dryBeta: number;       // extra loss per -100 % RH below optimum (ASSUMPTION)
  handlingPer100km: number; // fraction bruised per 100 km (ASSUMPTION, commodities.yaml)
  reeferSetC: number;    // set point if a reefer is used
  color: string;
}

export const CROPS: Record<CropId, Crop> = {
  tomato: { id: "tomato", label: "Tomato", hi: "टमाटर", mr: "टोमॅटो", refLifeH: 192, refTempC: 10,
    rhOpt: 90, rotAlpha: 2.0, dryBeta: 0.6, handlingPer100km: 0.01, reeferSetC: 12, color: "#ff5a5f" },
  orange: { id: "orange", label: "Nagpur orange", hi: "संतरा", mr: "संत्री", refLifeH: 2016, refTempC: 1,
    rhOpt: 90, rotAlpha: 1.5, dryBeta: 0.8, handlingPer100km: 0.005, reeferSetC: 6, color: "#ffa62b" },
  onion: { id: "onion", label: "Onion", hi: "प्याज", mr: "कांदा", refLifeH: 4380, refTempC: 0,
    rhOpt: 70, rotAlpha: 3.0, dryBeta: 0.2, handlingPer100km: 0.002, reeferSetC: 5, color: "#c77dff" },
};
