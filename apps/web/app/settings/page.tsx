"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Avatar } from "@/components/AccountMenu";
import { Icon, type IconName } from "@/components/Icon";
import { ChoiceRow, Notice, PageHeader, Section, Segmented, SwitchRow } from "@/components/ui";
import { DEFAULT_PROFILE, loadAccount, saveAccount } from "@/lib/account";
import type { Arrival, Mobility, Profile, StepsAbility, WalkRange } from "@/lib/types";

const MOBILITY: { id: Mobility; label: string; detail: string }[] = [
  { id: "manual_wheelchair", label: "Manual wheelchair", detail: "Self-propelled or pushed" },
  { id: "powered_wheelchair", label: "Powered wheelchair", detail: "Electric chair" },
  { id: "mobility_scooter", label: "Mobility scooter", detail: "Wider and needs a longer turning space" },
  { id: "walks_short_distances", label: "I walk, but only short distances", detail: "Perhaps with a stick, crutches or a frame" },
  { id: "other", label: "Other or prefer not to say", detail: "We will check the main step-free route" },
];
const WHEELED: Mobility[] = ["manual_wheelchair", "powered_wheelchair", "mobility_scooter"];

const WALK: { value: WalkRange; label: string }[] = [
  { value: "short", label: "Under 50 m" },
  { value: "medium", label: "50\u2013200 m" },
  { value: "long", label: "Over 200 m" },
];

const STEPS: { value: StepsAbility; label: string }[] = [
  { value: "none", label: "None" },
  { value: "few", label: "1\u20132 steps" },
  { value: "flight", label: "A flight, with a rail" },
];

const ARRIVAL: { id: Arrival; label: string; detail: string; icon: IconName }[] = [
  { id: "blue_badge", label: "Car, with a blue badge", detail: "We check blue badge bays and the distance to the door", icon: "car" },
  { id: "car", label: "Car", detail: "We check parking and the distance to the door", icon: "car" },
  { id: "taxi", label: "Taxi or drop-off", detail: "We look for the nearest step-free drop-off", icon: "pin" },
  { id: "public_transport", label: "Public transport", detail: "Bus, train or tram", icon: "map" },
  { id: "on_foot", label: "On foot or wheeling", detail: "Straight from nearby", icon: "walk" },
];

type BoolKey = "needs_seating" | "avoid_slopes" | "needs_assistance" | "hearing_support" | "visual_support" | "quiet_space" | "needs_toilet" | "companion";

const ON_THE_WAY: { key: BoolKey; label: string; detail: string }[] = [
  { key: "needs_seating", label: "I need places to sit", detail: "Rest points along the route and at my seat" },
  { key: "avoid_slopes", label: "Steep slopes are hard for me", detail: "Ramps steeper than 1:12 become a caution" },
  { key: "needs_assistance", label: "I'd like staff help on arrival", detail: "We check desk hours and pre-booking" },
];

const SENSES: { key: BoolKey; label: string; detail: string }[] = [
  { key: "hearing_support", label: "I use a hearing aid", detail: "We check the hearing loop has been tested" },
  { key: "visual_support", label: "I have low vision", detail: "Answers describe landmarks and signage" },
  { key: "quiet_space", label: "I prefer quiet spaces", detail: "We mention crowds and quieter times" },
  { key: "needs_toilet", label: "I need an accessible toilet", detail: "We check it is in working order" },
];

export default function SettingsPage() {
  const [name, setName] = useState("");
  const [profile, setProfile] = useState<Profile>(DEFAULT_PROFILE);
  const [width, setWidth] = useState("");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const a = loadAccount();
    if (a) {
      setName(a.name);
      setProfile(a.profile);
      setWidth(a.profile.chair_width_mm ? String(a.profile.chair_width_mm) : "");
      setSavedAt(a.updatedAt);
    }
  }, []);

  const update = (patch: Partial<Profile>) => {
    setProfile((p) => ({ ...p, ...patch }));
    setDirty(true);
    setJustSaved(false);
  };
  const toggle = (key: BoolKey, v: boolean) => update({ [key]: v } as Partial<Profile>);

  const wheeled = WHEELED.includes(profile.mobility);
  const answered = [
    name.trim() !== "",
    true,
    !!profile.walk_range,
    wheeled || !!profile.steps,
    !!profile.arrival,
    ON_THE_WAY.concat(SENSES).some((q) => profile[q.key]) || profile.free_text.trim() !== "",
  ];
  const progress = Math.round((answered.filter(Boolean).length / answered.length) * 100);

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    const w = width.trim() ? Number(width) : null;
    if (w !== null && (!Number.isFinite(w) || w < 400 || w > 1500)) {
      setError("Chair width should be between 400 and 1500 mm, or left empty.");
      document.getElementById("chair-width")?.focus();
      return;
    }
    setError(null);
    const next: Profile = {
      ...profile,
      chair_width_mm: wheeled ? w : null,
      steps: wheeled ? null : profile.steps,
      free_text: profile.free_text.trim(),
    };
    saveAccount({ name: name.trim(), profile: next });
    setProfile(next);
    setSavedAt(new Date().toISOString());
    setDirty(false);
    setJustSaved(true);
  };

  return (
    <form onSubmit={save} noValidate>
      <PageHeader
        title="Travel profile"
        subtitle="A few questions about how you get around. Ecstasy uses your answers to decide which parts of a venue matter for you and how strictly to judge them."
      />

      <div className="card mb-8 flex items-center gap-4 p-4">
        <Avatar name={name} size={56} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[20px] font-semibold">{name.trim() || "Guest"}</p>
          <p className="text-[15px] text-muted">
            {savedAt && !dirty ? `Saved ${new Date(savedAt).toLocaleDateString(undefined, { day: "numeric", month: "short" })} \u00b7 stored only on this device` : "Stored only on this device"}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-[13px] font-semibold text-muted">{progress}% complete</span>
          <span className="h-1.5 w-24 overflow-hidden rounded-full bg-card2" aria-hidden="true">
            <span className="block h-full rounded-full bg-fill transition-[width] duration-500" style={{ width: `${progress}%` }} />
          </span>
        </div>
      </div>

      <div className="grid items-start gap-8 lg:grid-cols-2">
        <div className="space-y-8">
          <Section id="about" title="About you" footer="Optional. Only used to greet you.">
            <div className="card p-3">
              <label htmlFor="name" className="sr-only">Your name</label>
              <input id="name" value={name} onChange={(e) => { setName(e.target.value); setDirty(true); setJustSaved(false); }} className="field" placeholder="What should we call you?" autoComplete="name" maxLength={60} />
            </div>
          </Section>

          <Section id="mobility" title="How do you usually get around?">
            <fieldset>
              <legend className="sr-only">How do you usually get around?</legend>
              <div className="list">
                {MOBILITY.map((m) => (
                  <ChoiceRow key={m.id} name="mobility" value={m.id} checked={profile.mobility === m.id}
                    onChange={() => update({ mobility: m.id })} title={m.label} detail={m.detail} />
                ))}
              </div>
            </fieldset>
          </Section>

          {wheeled && (
            <Section id="width" title="How wide is your chair or scooter?" footer="Optional. Measure at the widest point, including wheels and push rims. Paths narrower than this become a caution.">
              <div className="card flex items-center gap-3 p-3">
                <label htmlFor="chair-width" className="sr-only">Chair or scooter width in millimetres</label>
                <input id="chair-width" inputMode="numeric" value={width} onChange={(e) => { setWidth(e.target.value.replace(/[^\d]/g, "").slice(0, 4)); setDirty(true); }}
                  className="field" placeholder="e.g. 680" aria-describedby="width-unit" />
                <span id="width-unit" className="shrink-0 pr-2 text-[17px] text-muted">mm</span>
              </div>
            </Section>
          )}

          <Section id="distance" title="Distance and steps">
            <div className="card space-y-4 p-4">
              <div className="space-y-2">
                <p className="text-[15px] font-semibold">How far can you go before you need a rest?</p>
                <Segmented label="How far can you go before you need a rest?" value={profile.walk_range ?? undefined} options={WALK} onChange={(v) => update({ walk_range: v })} />
              </div>
              {!wheeled && (
                <div className="space-y-2">
                  <p className="text-[15px] font-semibold">How many steps can you manage?</p>
                  <Segmented label="How many steps can you manage?" value={profile.steps ?? undefined} options={STEPS} onChange={(v) => update({ steps: v })} />
                </div>
              )}
            </div>
          </Section>
        </div>

        <div className="space-y-8">
          <Section id="way" title="On the way">
            <div className="list">
              {ON_THE_WAY.map((q) => (
                <SwitchRow key={q.key} label={q.label} detail={q.detail} checked={!!profile[q.key]} onChange={(v) => toggle(q.key, v)} />
              ))}
            </div>
          </Section>

          <Section id="senses" title="Senses and comfort">
            <div className="list">
              {SENSES.map((q) => (
                <SwitchRow key={q.key} label={q.label} detail={q.detail} checked={!!profile[q.key]} onChange={(v) => toggle(q.key, v)} />
              ))}
            </div>
          </Section>

          <Section id="arrival" title="How do you usually arrive?">
            <fieldset className="space-y-3">
              <legend className="sr-only">How do you usually arrive?</legend>
              <div className="list" style={{ ["--inset" as string]: "64px" }}>
                {ARRIVAL.map((a) => (
                  <ChoiceRow key={a.id} name="arrival" value={a.id} checked={profile.arrival === a.id} onChange={() => update({ arrival: a.id })}
                    title={a.label} detail={a.detail}
                    leading={
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-brand-bg text-brand" aria-hidden="true">
                        <Icon name={a.icon} className="h-5 w-5" />
                      </span>
                    } />
                ))}
              </div>
              <div className="list">
                <SwitchRow label="I usually travel with a companion or carer" detail="Answers include tips for whoever is with you"
                  checked={!!profile.companion} onChange={(v) => update({ companion: v })} />
              </div>
            </fieldset>
          </Section>

          <Section id="else" title="Anything else?" footer="In your own words, for example: I get tired after about ten minutes, or my chair cannot tilt back.">
            <div className="card p-3">
              <label htmlFor="free" className="sr-only">Anything else about your needs</label>
              <textarea id="free" value={profile.free_text} onChange={(e) => update({ free_text: e.target.value.slice(0, 400) })}
                rows={3} className="field min-h-[96px] resize-none" placeholder="Anything the questions above missed" />
            </div>
          </Section>
        </div>
      </div>

      <div className="sticky bottom-[calc(env(safe-area-inset-bottom)+92px)] z-20 mt-8 space-y-3 md:bottom-6">
        <div aria-live="polite">
          {error && <Notice tone="bad">{error}</Notice>}
          {!error && justSaved && (
            <Notice tone="ok">
              Saved. Your next route check uses this profile.{" "}
              <Link href="/plan" className="underline underline-offset-2">Check my route</Link>
            </Notice>
          )}
        </div>
        <button type="submit" disabled={!dirty} className="btn btn-primary w-full text-[18px] md:mx-auto md:flex md:max-w-md">
          <Icon name="checkCircle" className="h-5 w-5" />
          {dirty ? "Save travel profile" : savedAt ? "All changes saved" : "Answer a question to save"}
        </button>
      </div>
    </form>
  );
}
