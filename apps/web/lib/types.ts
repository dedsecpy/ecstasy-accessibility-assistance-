export type Verdict = "go" | "caution" | "no_go";
export type Mobility = "manual_wheelchair" | "powered_wheelchair" | "mobility_scooter" | "walks_short_distances" | "other";

export type WalkRange = "short" | "medium" | "long";
export type StepsAbility = "none" | "few" | "flight";
export type Arrival = "blue_badge" | "car" | "taxi" | "public_transport" | "on_foot";

export interface Profile {
  mobility: Mobility;
  mobility_note?: string;
  needs_seating: boolean;
  avoid_slopes: boolean;
  needs_assistance: boolean;
  free_text: string;
  walk_range?: WalkRange | null;
  steps?: StepsAbility | null;
  chair_width_mm?: number | null;
  hearing_support?: boolean;
  visual_support?: boolean;
  quiet_space?: boolean;
  needs_toilet?: boolean;
  arrival?: Arrival | null;
  companion?: boolean;
}

export interface AskRequest {
  question: string;
  profile: Profile;
  event_id: string | null;
  visit_at?: string | null;
}

export interface Cited {
  text: string;
  citations: string[];
}

export interface AnswerBody {
  verdict: Verdict;
  headline: string;
  summary: string;
  route: Cited[];
  warnings: Cited[];
  verify: string[];
  discrepancies: Cited[];
}

export interface LiveItem {
  sid: string;
  feature: string;
  label: string;
  status: string;
  status_label: string;
  source_kind: string;
  source_label: string;
  observed_at: string;
  age_s: number;
  age_text: string;
  stale: boolean;
  conflict: boolean;
  sensor_offline: boolean;
  blocking: boolean;
  note: string;
  required: boolean;
}

export interface PassageT {
  pid: string;
  chunk_id: string;
  doc_id: string;
  doc_title: string;
  source_type: string;
  trust: string;
  date: string;
  heading: string;
  text: string;
  scores: Record<string, number>;
}

export interface AskResult {
  answer: AnswerBody;
  mode: "llm" | "fallback";
  ai: {
    mode: string;
    provider: string | null;
    bedrock_enabled: boolean;
    llm_model: string | null;
    embedder: string | null;
    embedder_reason: string | null;
    rerank: string | null;
    planner: string | null;
    error: string | null;
  };
  visit: {
    destination: string | null;
    needs_lift: boolean;
    visit_at: string | null;
    staffed: boolean | null;
    staffed_window: string;
    event_name: string | null;
    phone: string;
  };
  required_features: string[];
  live: LiveItem[];
  passages: PassageT[];
  validation: { hard_problems: string[]; fixes: string[]; ok: boolean };
  retrieval: Record<string, unknown>;
  latency_ms: number;
  generated_at: string;
  trace_id?: number;
}

export interface Evidence {
  obs_id: number | null;
  source_kind: string;
  status: string;
  note: string;
  observed_at: string;
  age_s: number;
  expired: boolean;
  confidence: number;
}

export interface FeatureState {
  feature: string;
  label: string;
  status: string;
  status_label: string;
  confidence: number;
  source_kind: string;
  note: string;
  observed_at: string;
  age_s: number;
  stale: boolean;
  conflict: boolean;
  sensor_offline: boolean;
  blocking: boolean;
  freshness: string;
  evidence: Evidence[];
}

export interface Alert {
  id: number;
  feature: string;
  kind: string;
  severity: "high" | "medium" | "info";
  message: string;
  acked: boolean;
  created_at: string;
}

export interface VenueEvent {
  id: string;
  name: string;
  start: string;
  doors?: string;
  location: string;
}

export interface VenueSummary {
  id: string;
  name: string;
  events: VenueEvent[];
  city?: string | null;
  area?: string | null;
  kind?: string | null;
  tags?: string[] | null;
  blurb?: string | null;
  demo?: boolean | null;
}

export interface Venue extends VenueSummary {
  assistance_phone: string;
  hours_text: string;
  listing_updated: string;
  local_time: string;
  scenario: string;
  locations: Record<string, { floor: number; needs_lift: boolean }>;
  labels?: Record<string, string>;
}

export interface Health {
  status: string;
  ai: {
    label: string;
    provider: "groq" | "bedrock" | "local";
    provider_label: string;
    credentials_present: boolean;
    bedrock_enabled: boolean;
    aws_credentials_present: boolean;
    llm_model: string;
    fast_llm_model: string;
    embed_model: string;
    rerank_model: string | null;
    region: string | null;
    index: { embedder_label?: string; collection?: string; chunks?: number; reason?: string };
  };
}
