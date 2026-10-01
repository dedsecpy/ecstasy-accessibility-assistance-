"use client";

import { useEffect, useState } from "react";
import type { Profile } from "./types";

/*
 * The visitor's account lives on this device only: a display name, the travel-profile
 * questionnaire and an appearance preference. Signing out removes all of it.
 */

const ACCOUNT_KEY = "ecstasy.account.v1";
const THEME_KEY = "ecstasy.theme";
const CHANGE_EVENT = "ecstasy:account";

export type Theme = "system" | "light" | "dark";

export interface Account {
  name: string;
  profile: Profile;
  updatedAt: string;
}

export const DEFAULT_PROFILE: Profile = {
  mobility: "manual_wheelchair",
  needs_seating: false,
  avoid_slopes: false,
  needs_assistance: false,
  free_text: "",
  walk_range: null,
  steps: null,
  chair_width_mm: null,
  hearing_support: false,
  visual_support: false,
  quiet_space: false,
  needs_toilet: false,
  arrival: null,
  companion: false,
};

export function loadAccount(): Account | null {
  try {
    const raw = localStorage.getItem(ACCOUNT_KEY);
    if (!raw) return null;
    const a = JSON.parse(raw) as Account;
    return { ...a, profile: { ...DEFAULT_PROFILE, ...a.profile } };
  } catch {
    return null;
  }
}

export function saveAccount(a: Omit<Account, "updatedAt">) {
  try {
    localStorage.setItem(ACCOUNT_KEY, JSON.stringify({ ...a, updatedAt: new Date().toISOString() }));
  } catch {
    /* storage full or disabled */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Removes every Ecstasy item from this device, including the saved plan and answer. */
export function signOut() {
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith("ecstasy.") || k.startsWith("nimbus."))
      .forEach((k) => localStorage.removeItem(k));
  } catch {
    /* storage disabled */
  }
  applyTheme("system");
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useAccount(): Account | null {
  const [account, setAccount] = useState<Account | null>(null);
  useEffect(() => {
    const sync = () => setAccount(loadAccount());
    sync();
    window.addEventListener(CHANGE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return account;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");
}

/* ---------------------------------------------------------------- appearance */

export function loadTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: Theme) {
  try {
    if (theme === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* storage disabled */
  }
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", dark ? "#000000" : "#f2f2f7"));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    setTheme(loadTheme());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => loadTheme() === "system" && applyTheme("system");
    mq.addEventListener("change", follow);
    return () => mq.removeEventListener("change", follow);
  }, []);
  return [theme, (t) => { setTheme(t); applyTheme(t); }];
}
