"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Avatar } from "@/components/AccountMenu";
import { Icon } from "@/components/Icon";
import { MobilityPicker } from "@/components/MobilityPicker";
import { ChoiceRow, Notice, PageHeader, Section, SwitchRow } from "@/components/ui";
import { VenueSearch } from "@/components/VenueSearch";
import { DEFAULT_PROFILE, loadAccount, useAccount } from "@/lib/account";
import { api, askStream, currentVenueId, setCurrentVenue, VENUE_ID } from "@/lib/api";
import { useSpeech } from "@/lib/hooks";
import { loadPlan, savePlan } from "@/lib/store";
import type { Profile, Venue, VenueSummary } from "@/lib/types";

const NEEDS: { key: "needs_seating" | "avoid_slopes" | "needs_assistance"; label: string; detail: string }[] = [
  { key: "needs_seating", label: "I need places to sit", detail: "Rest points along the route" },
  { key: "avoid_slopes", label: "I can't manage steep slopes", detail: "Avoid ramps steeper than 1:12" },
  { key: "needs_assistance", label: "I'd like staff help on arrival", detail: "Checks desk hours and pre-booking" },
];

function fmtEvent(start: string) {
  const d = new Date(start);
  return d.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function profileHighlights(p: Profile): string[] {
  const out: string[] = [];
  if (p.chair_width_mm) out.push(`${p.chair_width_mm} mm chair`);
  if (p.walk_range === "short") out.push("Rests under 50 m");
  if (p.steps === "none") out.push("No steps");
  if (p.hearing_support) out.push("Hearing loop");
  if (p.visual_support) out.push("Low vision");
  if (p.quiet_space) out.push("Quiet spaces");
  if (p.needs_toilet) out.push("Accessible toilet");
  if (p.arrival === "blue_badge") out.push("Blue badge");
  else if (p.arrival === "car") out.push("Arriving by car");
  else if (p.arrival === "taxi") out.push("Drop-off");
  if (p.companion) out.push("With a companion");
  return out;
}

function ProfileCard() {
  const account = useAccount();
  if (!account) {
    return (
      <Link href="/settings" className="card row gap-4 p-4 transition-colors hover:bg-card2">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-bg text-brand" aria-hidden="true">
          <Icon name="person" className="h-6 w-6" stroke={2} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">Set up your travel profile</span>
          <span className="block text-[15px] leading-snug text-muted">Answer a few questions so every route check fits how you travel.</span>
        </span>
        <Icon name="chevron" className="h-4 w-4 shrink-0 text-muted" stroke={2.2} />
      </Link>
    );
  }
  const chips = profileHighlights(account.profile);
  return (
    <Link href="/settings" className="card row gap-4 p-4 transition-colors hover:bg-card2">
      <Avatar name={account.name} size={44} />
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">Personalised for {account.name.trim() || "you"}</span>
        {chips.length ? (
          <span className="mt-1.5 flex flex-wrap gap-1.5">
            {chips.map((c) => <span key={c} className="badge bg-card2 px-2.5 py-0.5 text-[13px] text-ink">{c}</span>)}
          </span>
        ) : (
          <span className="block text-[15px] text-muted">Your travel profile is applied to this check.</span>
        )}
      </span>
      <span className="sr-only">Edit travel profile</span>
      <Icon name="chevron" className="h-4 w-4 shrink-0 text-muted" stroke={2.2} />
    </Link>
  );
}

export default function PlanPage() {
  const router = useRouter();
  const [venue, setVenue] = useState<Venue | null>(null);
  const [eventId, setEventId] = useState<string>("");
  const [profile, setProfile] = useState<Profile>(DEFAULT_PROFILE);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<{ stage: string; message: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const speech = useSpeech((t) => setQuestion((q) => (q ? `${q} ${t}` : t)));

  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    const id = currentVenueId();
    (id === VENUE_ID ? api.venue(id) : api.venue(id).catch(() => api.venue(VENUE_ID))).then((v) => {
      setVenue(v);
      const saved = loadPlan();
      const account = loadAccount();
      if (account && (!saved || account.updatedAt > saved.savedAt)) setProfile(account.profile);
      else if (saved) setProfile({ ...DEFAULT_PROFILE, ...saved.request.profile });
      if (saved) setQuestion(saved.request.question);
      if (saved && (saved.venueId || VENUE_ID) === v.id) setEventId(saved.request.event_id || "");
      else setEventId(v.events[0]?.id || "");
    }).catch((e) => setError(`Cannot reach the Ecstasy API: ${e.message}`));
  }, []);

  const pickVenue = (v: VenueSummary) => {
    if (v.id === venue?.id) return;
    setCurrentVenue(v.id);
    setSwitching(true);
    setError(null);
    api.venue(v.id)
      .then((full) => {
        setVenue(full);
        setEventId(full.events[0]?.id || "");
      })
      .catch((e) => setError(`Could not load ${v.name}: ${e.message}`))
      .finally(() => setSwitching(false));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!venue) return;
    setBusy(true);
    setError(null);
    setSteps([]);
    progressRef.current?.focus();
    const request = { question, profile, event_id: eventId || null };
    try {
      const result = await askStream(request, (stage, message) => setSteps((s) => [...s, { stage, message }]), venue.id);
      savePlan({ request, result, savedAt: new Date().toISOString(), venueId: venue.id, venueName: venue.name });
      router.push("/answer");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-describedby="plan-intro">
      <PageHeader
        title="Plan your visit"
        subtitle={
          <span id="plan-intro">
            {venue ? <strong className="font-semibold text-ink">{venue.name}. </strong> : "Loading venue. "}
            Ecstasy checks live lift, gate and path status and the venue&apos;s records, then tells you honestly whether you can get
            from arrival to your seat.
          </span>
        }
      />

      <div className="mb-8 lg:max-w-[calc(50%-16px)]">
        <ProfileCard />
      </div>

      <div className="grid items-start gap-8 lg:grid-cols-2">
        <div className="min-w-0 space-y-8">
          <Section id="event" title="Event">
            <VenueSearch currentId={venue?.id ?? null} onSelect={pickVenue} />

            {venue && (
              <div className="card row gap-3 p-4" aria-live="polite">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-fill text-white" aria-hidden="true">
                  <Icon name="building" className="h-5 w-5" stroke={2} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold uppercase tracking-wide text-muted">Events at</span>
                  <span className="block font-semibold leading-snug">{venue.name}</span>
                  {(venue.area || venue.kind) && (
                    <span className="block text-[15px] leading-snug text-muted">{[venue.area, venue.city, venue.kind].filter(Boolean).join(" \u00b7 ")}</span>
                  )}
                </span>
                {switching ? (
                  <span className="spinner shrink-0 text-brand" aria-label="Loading venue" />
                ) : venue.demo ? (
                  <span className="badge shrink-0 bg-unsure-bg px-2.5 py-1 text-[12px] text-unsure" title="Illustrative sample data, not verified accessibility information">Sample data</span>
                ) : null}
              </div>
            )}

            <fieldset>
              <legend className="sr-only">Which event?</legend>
              <div className={`list transition-opacity ${switching ? "opacity-50" : ""}`} style={{ ["--inset" as string]: "64px" }}>
                {venue?.events.map((ev) => {
                  const up = venue.locations[ev.location]?.needs_lift;
                  return (
                    <ChoiceRow
                      key={ev.id}
                      name="event"
                      value={ev.id}
                      checked={eventId === ev.id}
                      onChange={() => setEventId(ev.id)}
                      leading={
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-brand-bg text-brand" aria-hidden="true">
                          <Icon name="calendar" className="h-5 w-5" />
                        </span>
                      }
                      title={ev.name}
                      detail={`${fmtEvent(ev.doors || ev.start)} \u00b7 ${ev.location} \u00b7 ${up ? "Upstairs" : "Ground floor"}`}
                    />
                  );
                })}
                <ChoiceRow
                  name="event"
                  value=""
                  checked={eventId === ""}
                  onChange={() => setEventId("")}
                  leading={
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-card2 text-muted" aria-hidden="true">
                      <Icon name="pin" className="h-5 w-5" />
                    </span>
                  }
                  title="Just visiting"
                  detail="Not sure yet, or no event"
                />
                {!venue && !error && <div className="row text-muted"><span className="spinner" aria-hidden="true" /> Loading events</div>}
              </div>
            </fieldset>
          </Section>

          <Section id="mobility" title="How you get around">
            <MobilityPicker
              value={profile.mobility}
              note={profile.mobility_note || ""}
              onChange={(m) => setProfile((p) => ({ ...p, mobility: m }))}
              onNote={(t) => setProfile((p) => ({ ...p, mobility_note: t }))}
            />
          </Section>
        </div>

        <div className="space-y-8 lg:sticky lg:top-12">
          <Section id="needs" title="Your needs" footer="Changes here apply to this check only. Edit your travel profile to change them for every visit.">
            <div className="list">
              {NEEDS.map((n) => (
                <SwitchRow
                  key={n.key}
                  label={n.label}
                  detail={n.detail}
                  checked={profile[n.key]}
                  onChange={(v) => setProfile({ ...profile, [n.key]: v })}
                />
              ))}
            </div>
          </Section>

          <Section id="question" title="Your question" footer="Optional. Ask in your own words, or use the microphone.">
            <div className="card p-3">
              <label htmlFor="q" className="sr-only">Your question (optional)</label>
              <div className="flex items-start gap-2">
                <textarea
                  id="q"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  rows={3}
                  placeholder="e.g. Can I get to the lecture and sit near the front?"
                  className="field min-h-[96px] resize-none"
                />
                {speech.supported && (
                  <button
                    type="button"
                    onClick={speech.toggle}
                    aria-pressed={speech.listening}
                    aria-label={speech.listening ? "Stop dictation" : "Dictate your question"}
                    className={`tap flex shrink-0 items-center justify-center rounded-full transition-colors ${
                      speech.listening ? "bg-bad-bg text-bad motion-safe:animate-pulse" : "bg-brand-bg text-brand"
                    }`}
                  >
                    <Icon name="mic" className="h-5 w-5" />
                  </button>
                )}
              </div>
            </div>
          </Section>

          <div className="space-y-4">
            <button type="submit" disabled={busy || !venue} aria-busy={busy} className="btn btn-primary w-full text-[18px]">
              {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="sparkle" className="h-5 w-5" />}
              {busy ? "Checking your route" : "Check my route"}
            </button>

            <div ref={progressRef} tabIndex={-1} aria-live="polite" className="outline-none">
              {steps.length > 0 && (
                <ol className="list fade-in" style={{ ["--inset" as string]: "48px" }}>
                  {steps.map((s, i) => {
                    const current = i === steps.length - 1 && busy;
                    return (
                      <li key={i} className="row min-h-[44px] py-2.5 text-[15px]">
                        <span className={`flex h-5 w-5 shrink-0 items-center justify-center ${current ? "text-brand" : "text-ok"}`} aria-hidden="true">
                          {current ? <span className="spinner" /> : <Icon name="checkCircle" className="h-5 w-5" />}
                        </span>
                        <span className={current ? "font-semibold" : "text-muted"}>{s.message}</span>
                      </li>
                    );
                  })}
                </ol>
              )}
              {error && <div className="mt-3"><Notice tone="bad">{error}</Notice></div>}
            </div>
          </div>
        </div>
      </div>
    </form>
  );
}
