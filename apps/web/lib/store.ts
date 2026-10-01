import type { AskRequest, AskResult } from "./types";

const PLAN_KEY = "nimbus.plan.v2";

export interface SavedPlan {
  request: AskRequest;
  result: AskResult;
  savedAt: string;
}

export function savePlan(p: SavedPlan) {
  try {
    localStorage.setItem(PLAN_KEY, JSON.stringify(p));
  } catch {
    /* storage full or disabled */
  }
}

export function loadPlan(): SavedPlan | null {
  try {
    const raw = localStorage.getItem(PLAN_KEY);
    return raw ? (JSON.parse(raw) as SavedPlan) : null;
  } catch {
    return null;
  }
}

export function ageText(observedAt: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(observedAt).getTime()) / 1000));
  if (s < 90) return `${s} s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export const PHONE_RE = /(\+?\d[\d\s]{7,}\d)/;
