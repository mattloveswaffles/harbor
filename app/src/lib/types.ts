// Shapes returned by the Harbor backend (docs/API.md). Money is integer cents; times are ISO 8601 UTC.
import type { FeatureCollection } from 'geojson';

export type RiskLevel = 'clear' | 'monitor' | 'prepare' | 'act' | 'shelter' | 'recover';
export interface LatLon {
  lat: number;
  lon: number;
}

export interface Household {
  adults: number;
  children_ages: number[];
  seniors: number;
  pets: { type: string; count: number }[];
  mobility: 'none' | 'walker' | 'wheelchair';
  has_car: boolean;
  home_type: 'site_built' | 'mobile';
  evac_zone: string;
}

export interface User {
  id: string;
  name: string;
  zip: string;
  location: LatLon;
  household: Household;
  risk_level: RiskLevel;
}

export interface AuthOut {
  token: string;
  expires_at: string;
  user: User;
}
export interface ZipInfo {
  zip: string;
  city: string;
  state: string;
  lat: number;
  lon: number;
}

export interface Health {
  ok: boolean;
  mode: 'demo' | 'live';
  nessie: string;
  nhc: string;
  ai: string;
  chat: 'ok' | 'off';
  clock: string;
}

export interface Account {
  id: string;
  type: 'checking' | 'savings' | 'brokerage_cash' | 'wallet';
  nickname: string;
  balance_cents: number;
  balance_synced_at: string;
}

export interface Portfolio {
  total_value_cents: number;
  disclaimer: string;
  holdings: { symbol: string; name: string; shares: number; value_cents: number }[];
}

export interface Alert {
  type: string;
  headline: string;
  issued: string;
  expires: string;
}
export interface StormStatus {
  server_time: string;
  risk_level: RiskLevel;
  risk_reason: string;
  storm: null | {
    name: string;
    classification: string;
    category: number | null;
    advisory_number: string;
    advisory_time: string;
    headline: string;
    max_wind_mph: number;
  };
  at_your_zip: {
    ts_wind_probability_5day: number;
    hurricane_wind_probability_5day: number;
    in_forecast_cone: boolean;
    earliest_ts_winds_eta: string | null;
    alerts: Alert[];
  };
}

export type MoveKind =
  | 'transfer'
  | 'sell_etf'
  | 'withdraw_cash'
  | 'defer_bill'
  | 'log_purchase'
  | 'restore_transfer'
  | 'rebuy_etf';
export type MoveStatus =
  | 'proposed'
  | 'scheduled'
  | 'executing'
  | 'pending_settlement'
  | 'done'
  | 'cancelled'
  | 'failed';
export interface Move {
  id: string;
  kind: MoveKind;
  status: MoveStatus;
  symbol: string | null;
  amount_cents: number;
  scheduled_for: string;
  expected_available_at: string | null;
  cancel_deadline: string | null;
  why: string;
  error: { code: string; message: string } | null;
}

export type PlanStatus =
  | 'draft'
  | 'awaiting_approval'
  | 'approved'
  | 'running'
  | 'complete'
  | 'restoring'
  | 'restored'
  | 'cancelled'
  | 'expired'
  | 'superseded';
export interface Plan {
  id: string;
  version: number;
  status: PlanStatus;
  cash_needed_by: string;
  latest_safe_approval_at: string | null;
  budget: { total_cents: number; lines: { label: string; amount_cents: number; source: string }[] };
  sources: { already_in_checking_cents: number; from_savings_cents: number; from_etf_sales_cents: number };
  shortfall_cents: number;
  help_resources: { label: string; phone?: string; url?: string }[];
  moves: Move[];
  alternatives: { id: string; label: string; feasible: boolean; why_not: string | null; total_cents?: number }[];
  summary: string;
  warnings: string[];
}

export interface Destination {
  id: string;
  name: string;
  location: LatLon;
  drive_time_min_normal: number;
  drive_time_min_evac: number;
  outside_cone: boolean;
  recommended: boolean;
  feasible?: boolean;
}

type YesNo = 'yes' | 'no' | 'unknown';

/** A FEMA Open Shelters record (live, or recorded for the Milton replay). */
export interface Shelter {
  id: string;
  name: string;
  address: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  status: 'open' | 'full' | 'closed';
  capacity: number | null;
  population: number | null;
  org: string | null;
  hours: string | null;
  kind: 'general' | 'special_needs';
  pets: YesNo;
  ada: YesNo;
  wheelchair: YesNo;
  distance_mi: number;
  location: LatLon;
  source: string;
  links: { google: string; apple: string };
}

export interface Guide {
  server_time: string;
  decision: { action: 'evacuate' | 'shelter_in_place' | 'use_public_shelter'; reason_codes: string[] };
  leave_by: string | null;
  destinations: Destination[];
  chosen: string | null;
  route: null | {
    distance_mi: number;
    drive_time_min_normal: number;
    drive_time_min_evac: number;
    drive_time_note: string;
    corridor: string | null;
    links: { google: string; apple: string };
  };
  shelters: Shelter[];
  lodging: null | {
    nights: number;
    nightly_estimate_cents: number;
    options: { id: string; name: string; type: string; pets: string }[];
  };
  checklists: { need: string; items: string[]; source_url: string }[];
  advice_cards: { kind: string; title: string; text: string; url?: string }[];
}

export interface MapLayers {
  home: FeatureCollection;
  cone: FeatureCollection;
  track: FeatureCollection;
  route: FeatureCollection;
  route_options: FeatureCollection;
  destinations: FeatureCollection;
  shelters: FeatureCollection;
  lodging: FeatureCollection;
  atms: FeatureCollection;
  sensors: FeatureCollection;
}
export interface MapOut {
  server_time: string;
  layers: MapLayers;
  attribution: string[];
}

export interface HarborEvent {
  id: string;
  at: string;
  type: string;
  message: string;
  data: Record<string, unknown>;
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}
/** One server-sent event of a streamed Ask Harbor answer. */
export type ChatEvent =
  | { type: 'thinking' | 'text'; text: string }
  | { type: 'tool'; name: string }
  | { type: 'done'; tools_used: string[] }
  | { type: 'error'; code: string; message: string };

/** The Settings popup (GET/PUT /me/profile). */
export interface Profile {
  personal: { name: string; dob: string; phone: string; email: string; language: 'en' | 'es' };
  home: { address: string; home_type: 'house' | 'apartment' | 'mobile'; evac_zone: string };
  people: { name: string; age: number | null; relation: string }[];
  pets: { name: string; type: string; weight_lb: number | null; notes: string }[];
  medical: {
    medications: { name: string; dose: string; person: string; schedule: string; days_left: number | null }[];
    equipment: string[];
    needs_power: boolean;
    oxygen: boolean;
    dialysis: boolean;
    refrigerated_meds: boolean;
    mobility: 'none' | 'walker' | 'wheelchair';
    allergies: string;
    pharmacy: string;
  };
  vehicle: {
    has_car: boolean;
    make_model: string;
    mpg: number | null;
    tank_gal: number | null;
    fuel_level: number;
    seats: number | null;
    towing: boolean;
  };
  places: { label: string; address: string; kind: 'destination' | 'work' | 'school' | 'other' }[];
  contacts: { name: string; relation: string; phone: string; gets_plan: boolean }[];
  alerts: { sms: boolean; email: boolean; push: boolean; quiet_hours: boolean; tell_contacts: boolean };
  privacy: { share_location: boolean; medical_for_planning_only: boolean };
}
export type ProfileSave = Profile & { zip?: string; location?: LatLon };

export interface Connection {
  id: string;
  name: string;
  kind: 'bank' | 'brokerage' | 'wallet';
  connected: boolean;
  accounts: { id: string; type: Account['type']; nickname: string; balance_cents: number }[];
  total_cents: number;
}

export interface AdviceStep {
  title: string;
  detail: string;
  kind: 'money' | 'car' | 'medicine' | 'pet' | 'packing' | 'shelter';
}
/** Written by the AI in the background: `advice` is the last answer (null until the first one lands). */
export interface Advice {
  status: 'running' | 'ready' | 'error';
  error: string | null;
  updated_at: string;
  advice: {
    summary: string;
    destination_id: string;
    shelter_id: string | null;
    steps: AdviceStep[];
  } | null;
  facts: {
    available_cents: number;
    trip_total_cents: number;
    budget_lines: { label: string; amount_cents: number }[];
    connected: string[];
    leave_by: string | null;
    storm_winds_at: string | null;
    range_mi: number | null;
    route_mi: number | null;
  };
}

export type Level = 'likely' | 'possible' | 'unlikely';
export interface Weather {
  storm: null | {
    name: string;
    classification: string;
    category: number | null;
    max_wind_mph: number;
    warning: string | null;
    closest_at: string | null;
    closest_miles: number | null;
    category_at_closest: number | null;
  };
  hazards: {
    wind: { arrives_at: string | null; peak_wind_mph: number; peak_gust_mph: number };
    surge: { zone: string; level: 'evacuate' | 'low' };
    rain: { total_in: number };
    tornado: { level: 'watch' | 'possible' | 'unlikely' };
    power: { level: Level };
  };
  step_hours: number;
  series: { at: string; wind_mph: number; gust_mph: number; rain_in: number }[];
  marks: { leave_by: string | null; closest_at: string | null };
  source: string;
}

export interface Atm {
  id: string;
  name: string;
  distance_miles: number;
  in_forecast_cone: boolean;
  on_evacuation_route: boolean;
}
