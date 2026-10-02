import type { Alert, AskRequest, AskResult, FeatureState, Health, Venue, VenueSummary } from "./types";

export const VENUE_ID = process.env.NEXT_PUBLIC_VENUE_ID || "riverside_hall";
const VENUE_KEY = "ecstasy.venue";
export const VENUE_EVENT = "ecstasy:venue";

/** The venue the visitor last picked (stored on this device), else the default venue. */
export function currentVenueId(): string {
  if (typeof window === "undefined") return VENUE_ID;
  try {
    const id = localStorage.getItem(VENUE_KEY);
    return id && /^[a-z0-9_-]+$/.test(id) ? id : VENUE_ID;
  } catch {
    return VENUE_ID;
  }
}

export function setCurrentVenue(id: string) {
  try {
    localStorage.setItem(VENUE_KEY, id);
  } catch {
    /* storage disabled: the choice lasts for this page only */
  }
  window.dispatchEvent(new CustomEvent(VENUE_EVENT, { detail: id }));
}

/**
 * On Vercel the API shares the web app's domain under /api, so requests stay same-origin.
 * Docker Compose and plain `next dev` set NEXT_PUBLIC_API_PORT=8000: the API then runs on that
 * port of the same host the phone loaded the app from.
 */
export function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  const port = process.env.NEXT_PUBLIC_API_PORT;
  if (typeof window !== "undefined") {
    return port ? `${window.location.protocol}//${window.location.hostname}:${port}` : "";
  }
  return `http://localhost:${port || 8000}`;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => json<Health>("/api/health"),
  venues: () => json<VenueSummary[]>("/api/venues"),
  venue: (id = currentVenueId()) => json<Venue>(`/api/venues/${id}`),
  status: (id = currentVenueId()) => json<{ features: FeatureState[]; scenario: string }>(`/api/venues/${id}/status`),
  alerts: (id = currentVenueId()) => json<Alert[]>(`/api/venues/${id}/alerts`),
  ack: (alertId: number, id = currentVenueId()) => json(`/api/venues/${id}/alerts/${alertId}/ack`, { method: "POST" }),
  listingHealth: (id = currentVenueId()) => json<ListingHealth>(`/api/venues/${id}/listing-health`),
  report: (body: { text: string; reporter: string; kind?: string; needs?: string }, id = currentVenueId()) =>
    json<{ id: number; status: string }>(`/api/venues/${id}/reports`, { method: "POST", body: JSON.stringify(body) }),
  reportStatus: (rid: number) => json<ReportStatus>(`/api/reports/${rid}`),
  staffCheck: (items: { feature: string; status: string; note: string }[], staff_name: string, id = currentVenueId()) =>
    json<{ id: number }>(`/api/venues/${id}/staff-checks`, { method: "POST", body: JSON.stringify({ staff_name, items }) }),
  scenario: (scenario: string, venue_id = currentVenueId()) =>
    json(`/api/sim/scenario`, { method: "POST", body: JSON.stringify({ venue_id, scenario }) }),
  scenarios: () => json<Record<string, string>>("/api/sim/scenarios"),
  reindex: () => json("/api/admin/reindex", { method: "POST" }),
};

export interface ReportStatus {
  id: number;
  status: "pending" | "processing" | "done" | "error";
  extraction: { facts: { feature: string; status: string; note: string; confidence: number }[]; summary: string; mode: string } | null;
  error: string | null;
}

export interface ListingHealth {
  claims: { claim: string; verdict: "supported" | "qualified" | "contradicted" | "unverified"; reasons: string[] }[];
  affected_events: { id: string; name: string; start: string; location: string; issues: string[] }[];
  unconfirmed_features: FeatureState[];
  listing_age_days: number | null;
  listing_updated: string;
  draft_listing: string;
  staff_actions: string[];
  mode: string;
  ai_label: string | null;
  error: string | null;
}

/** POST /ask/stream and read Server-Sent Events from the response body. */
export async function askStream(
  req: AskRequest,
  onProgress: (stage: string, message: string) => void,
  id = currentVenueId(),
): Promise<AskResult> {
  const r = await fetch(`${apiBase()}/api/venues/${id}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(req),
  });
  if (!r.ok || !r.body) throw new Error(`Ask failed: ${r.status}`);
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "progress") onProgress(payload.stage, payload.message);
      else if (event === "result") return payload as AskResult;
      else if (event === "error") throw new Error(payload.message || "Ask failed");
    }
  }
  throw new Error("The answer stream ended unexpectedly");
}
