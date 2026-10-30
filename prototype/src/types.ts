export type CropId = "grapes" | "tomato" | "onion";
export type DisruptionType =
  | "closure" | "partial_blockage" | "congestion" | "reduced_speed" | "construction" | "accident" | "poor_road" | "vehicle_restriction";

export interface Place {
  market_id: string | null;
  market: string;
  district?: string;
  state?: string;
  lon: number;
  lat: number;
  geocode_method?: string;
  geocode_confidence?: number;
  volume_t?: number;
  tomato_price_rs_q?: number | null;
  onion_price_rs_q?: number | null;
  grapes_price_rs_q?: number | null;
}

export interface Shipment {
  shipment_id: string;
  crop: CropId;
  kg: number;
  condition: string | null;
  packaging: string | null;
  loading: string;
  vehicle: string | null;
  refrigeration_ok: boolean;
  reefer_fail_at_h: number | null;
  handling_events: number;
  pre_dispatch_h: number;
  market_wait_h: number;
  dispatch_hour: number;
  dispatch_date: string;
  price_rs_kg: number | null;
  q10: number | null;
  breakdown_h: number;
}

export interface ConditionsIn {
  ambient_c: number;
  rh: number;
  traffic: number;
  extra_delay_h: number;
  road_quality: number;
  vibration: number;
}

export interface Disruption {
  id: string;
  type: DisruptionType;
  edges: number[];
  severity: number;
  start_h: number;
  end_h: number | null;
  heavy_only: boolean;
  alt_access: boolean;
  confirmed: boolean;
  label: string;
  coords: number[][][];
}

export interface Metrics {
  feasible: boolean;
  reason?: string;
  distance_km: number;
  travel_h: number;
  delay_h: number;
  wait_h: number;
  road_quality: number;
  vibration_risk_pct: number;
  mean_cargo_temp_c: number;
  max_cargo_temp_c: number;
  heat_degree_h: number;
  q_arrival: number;
  kg: number;
  physical_loss_kg: number;
  rejected_kg: number;
  downgraded_kg: number;
  grade_a_kg: number;
  wastage_kg: number;
  wastage_pct: number;
  saleable_kg: number;
  revenue_rs: number;
  transport_cost_rs: number;
  net_value_rs: number;
  total_h: number;
  arrival_day: number;
  arrival_clock: string;
  profile: [number, number][];
}

export interface Mark { kind: "blocked" | "blocked_wait" | "congested" | "poor"; edge: number; coords: number[][]; hours?: number }

export interface CandidateRoute {
  id: string;
  label: string;
  feasible: boolean;
  reason: string;
  arcs: number[];
  edges: number[];
  edge_km: number[];
  coords: number[][];
  metrics: Metrics;
  marks: Mark[];
}

export interface Economics {
  extra_km: number;
  extra_transport_rs: number;
  extra_fuel_l: number;
  produce_value_protected_rs: number;
  net_benefit_rs: number;
  kg_saved: number;
  cost_per_kg_saved_rs: number | null;
}

export interface SnappedPoint {
  node: number;
  lon: number;
  lat: number;
  snap_km: number;
  label: string;
  access_leg: boolean;
  geocode_method?: string;
}

export interface Plan {
  decision: "reroute" | "continue" | "no_feasible_route" | "original_blocked";
  explanation: string[];
  margin_rs: number;
  original_id: string | null;
  recommended_id: string | null;
  candidates: CandidateRoute[];
  economics?: Economics;
  origin: SnappedPoint;
  destination: SnappedPoint;
}

export interface DiversionOption {
  node: number;
  route_index: number;
  km_ahead: number;
  eta_h: number;
  eta_lo_h: number;
  deadline_h: number;
  net_value_rs: number;
  benefit_rs: number | null;
  distance_km: number;
  wastage_kg: number;
  saleable_kg: number;
  reachable: boolean;
  label: string;
}

export interface Alert {
  id: string;
  shipment_id: string;
  state: string;
  tier: "CRITICAL" | "HIGH" | "ADVISORY" | "MONITOR" | "EXPIRED" | "NONE";
  created_h: number;
  updated_h: number;
  deadline_h: number | null;
  alert_at_h: number | null;
  pnr_label: string | null;
  benefit_rs: number | null;
  slack_min?: number | null;
  at_risk?: boolean;
  chosen_option: number | null;
  snooze_until_h: number | null;
  payload: {
    reason: string;
    options: DiversionOption[];
    pnr: DiversionOption | null;
    stay_feasible: boolean;
    stay_net_rs: number | null;
    stay_wastage_kg: number | null;
    wait_and_see: boolean;
    recommended_decision_h: number | null;
    benefit_curve: [number, number][];
    option_arcs: number[][];
  };
}

export interface AlertQueue {
  now_h: number;
  alerts: Alert[];
  pending: number;
  workload_min: number;
  at_risk: string[];
  warning: string | null;
}
