"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { initials, signOut, useAccount, useTheme, type Theme } from "@/lib/account";
import { Icon } from "./Icon";
import { Segmented } from "./ui";

export function Avatar({ name, size = 36 }: { name?: string; size?: number }) {
  const text = name ? initials(name) : "";
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${text ? "text-white" : "bg-card2 text-muted"}`}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.4,
        background: text ? "linear-gradient(180deg,#a0a6b8 0%,#6b7184 100%)" : undefined,
      }}
    >
      {text || <Icon name="person" className="h-[58%] w-[58%]" stroke={2} />}
    </span>
  );
}

const THEMES: { value: Theme; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

/** The account button and its popover: travel profile, appearance, staff view and sign out. */
export function AccountMenu({ placement = "down" }: { placement?: "down" | "up" }) {
  const account = useAccount();
  const [theme, setTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const path = usePathname() || "/";
  const router = useRouter();
  const staff = path.startsWith("/staff");
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const name = account?.name?.trim() || "";

  const close = (refocus = true) => {
    setOpen(false);
    setConfirming(false);
    if (refocus) buttonRef.current?.focus();
  };

  useEffect(() => {
    setOpen(false);
    setConfirming(false);
  }, [path]);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    const onDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) close(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const doSignOut = () => {
    signOut();
    close();
    router.push("/plan");
  };

  const pos = placement === "up" ? "bottom-full left-0 mb-2 origin-bottom-left" : "top-full right-0 mt-2 origin-top-right";

  return (
    <div ref={rootRef} className={`relative ${placement === "up" ? "w-full" : ""}`}>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-haspopup="dialog"
        onClick={() => (open ? close() : setOpen(true))}
        className={
          placement === "up"
            ? "tap flex w-full items-center gap-3 rounded-[16px] p-2 text-left transition-colors hover:bg-card2"
            : "tap flex items-center justify-center rounded-full"
        }
      >
        <span className="sr-only">Account and settings{name ? `, signed in as ${name}` : ""}</span>
        <Avatar name={name} size={placement === "up" ? 40 : 34} />
        {placement === "up" && (
          <span className="min-w-0 flex-1" aria-hidden="true">
            <span className="block truncate text-[15px] font-semibold">{name || "Guest"}</span>
            <span className="block truncate text-[13px] text-muted">{account ? "Travel profile set up" : "Set up your travel profile"}</span>
          </span>
        )}
        {placement === "up" && <Icon name="chevron" className="h-4 w-4 -rotate-90 text-muted" stroke={2.2} />}
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Account and settings"
          className={`menu-pop absolute z-50 w-[min(320px,calc(100vw-24px))] overflow-hidden rounded-[22px] border border-line bg-card shadow-[0_24px_60px_-12px_rgba(0,0,0,0.35)] ${pos}`}
        >
          <div className="flex items-center gap-3 px-4 pb-3 pt-4">
            <Avatar name={name} size={48} />
            <div className="min-w-0">
              <p className="truncate text-[17px] font-semibold">{name || "Guest"}</p>
              <p className="text-[13px] leading-snug text-muted">
                {account ? "Applied to every route check" : "Answer a few questions for better routes"}
              </p>
            </div>
          </div>

          <div className="list mx-3 bg-card2" style={{ ["--inset" as string]: "52px" }}>
            <Link href="/settings" className="row min-h-[48px] py-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] bg-fill text-white" aria-hidden="true">
                <Icon name="person" className="h-[18px] w-[18px]" stroke={2} />
              </span>
              <span className="flex-1">Travel profile</span>
              <Icon name="chevron" className="h-4 w-4 text-muted" stroke={2.2} />
            </Link>
            <Link href={staff ? "/plan" : "/staff/check"} className="row min-h-[48px] py-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] bg-[#8e8e93] text-white" aria-hidden="true">
                <Icon name="swap" className="h-[16px] w-[16px]" stroke={2} />
              </span>
              <span className="flex-1">{staff ? "Switch to visitor view" : "Switch to staff view"}</span>
              <Icon name="chevron" className="h-4 w-4 text-muted" stroke={2.2} />
            </Link>
          </div>

          <div className="px-4 pb-1 pt-4">
            <p id={`${panelId}-theme`} className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <Icon name={theme === "dark" ? "moon" : "sun"} className="h-4 w-4" stroke={2} />
              Appearance
            </p>
            <Segmented label="Appearance" value={theme} options={THEMES} onChange={setTheme} />
          </div>

          <div className="p-3">
            {confirming ? (
              <div className="fade-in rounded-[16px] bg-bad-bg p-3">
                <p className="text-[15px] font-semibold text-bad">Sign out on this device?</p>
                <p className="mt-0.5 text-[13px] text-ink">Your travel profile, saved answer and appearance setting will be removed.</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => setConfirming(false)} className="btn btn-gray btn-sm">Cancel</button>
                  <button type="button" onClick={doSignOut} className="btn btn-sm bg-bad text-bg">Sign out</button>
                </div>
              </div>
            ) : (
              <button type="button" onClick={() => setConfirming(true)} className="row min-h-[48px] rounded-[14px] bg-card2 py-2.5 font-semibold text-bad">
                <Icon name="logout" className="h-5 w-5" stroke={2} />
                Sign out
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
