"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import { StatusBadge } from "@/components/Status";
import { PageHeader, Section, Segmented } from "@/components/ui";
import { api } from "@/lib/api";
import { useVenueStream } from "@/lib/hooks";

const ITEMS: { feature: string; label: string; options: { status: string; label: string }[] }[] = [
  { feature: "lift", label: "Lift (call to both floors, doors, alarm)", options: [
    { status: "ok", label: "Working" }, { status: "degraded", label: "Problem" }, { status: "out_of_service", label: "Out of service" }] },
  { feature: "side_gate", label: "Side Gate, Mill Lane", options: [
    { status: "locked_on_request", label: "Opens on request" }, { status: "ok", label: "Open" }, { status: "out_of_service", label: "Can't open" }] },
  { feature: "intercom", label: "Side Gate intercom", options: [
    { status: "ok", label: "Answered" }, { status: "out_of_service", label: "Not working" }] },
  { feature: "courtyard_path", label: "Courtyard path", options: [
    { status: "ok", label: "Clear" }, { status: "degraded", label: "Narrowed" }, { status: "out_of_service", label: "Blocked" }] },
  { feature: "ramp", label: "Ramp and handrail", options: [
    { status: "degraded", label: "Usable (steep)" }, { status: "out_of_service", label: "Closed" }] },
  { feature: "seating", label: "Foyer and route seating", options: [
    { status: "ok", label: "Available" }, { status: "degraded", label: "Limited" }] },
  { feature: "toilet", label: "Accessible toilet", options: [
    { status: "ok", label: "Open" }, { status: "out_of_service", label: "Out of order" }] },
  { feature: "hearing_loop", label: "Hearing loop (Main Hall)", options: [
    { status: "ok", label: "Tested OK" }, { status: "out_of_service", label: "Faulty" }] },
];

export default function DailyCheckPage() {
  const { features } = useVenueStream();
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const count = Object.keys(picked).length;

  const submit = async () => {
    const items = Object.entries(picked).map(([feature, status]) => ({ feature, status, note: notes[feature] || "" }));
    if (!items.length) return;
    setBusy(true);
    try {
      await api.staffCheck(items, name || "Staff");
      setMsg({ ok: true, text: `Saved ${items.length} check${items.length > 1 ? "s" : ""}. Live status updates within a few seconds.` });
      setPicked({});
      setNotes({});
    } catch (e) {
      setMsg({ ok: false, text: `Could not save: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Daily check"
        subtitle="One tap per item. Human checks are trusted for 24 hours (lift) and are the fallback whenever a sensor or camera goes silent."
      />
      <div className="space-y-8">
        <Section id="who" title="Checked by">
          <div className="card p-3 md:max-w-md">
            <label htmlFor="staff-name" className="sr-only">Your name</label>
            <input id="staff-name" value={name} onChange={(e) => setName(e.target.value)} className="field" placeholder="Your name" autoComplete="name" />
          </div>
        </Section>

        <Section id="items" title="Access features">
          <ul className="grid gap-3 lg:grid-cols-2">
            {ITEMS.map((it) => {
              const cur = features[it.feature];
              const sel = picked[it.feature];
              return (
                <li key={it.feature} className={`card p-4 transition-shadow ${sel ? "ring-2 ring-brand" : ""}`}>
                  <fieldset className="min-w-0 space-y-3">
                    <legend className="text-[17px] font-semibold leading-tight">{it.label}</legend>
                    {cur && (
                      <p className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
                        Now <StatusBadge status={cur.status} label={cur.status_label} size="sm" />
                      </p>
                    )}
                    <Segmented
                      label={`${it.label}: result`}
                      value={sel}
                      options={it.options.map((o) => ({ value: o.status, label: o.label }))}
                      onChange={(v) => setPicked({ ...picked, [it.feature]: v })}
                    />
                    {sel && (
                      <input aria-label={`Note for ${it.label}`} placeholder="Add a note (optional)" value={notes[it.feature] || ""}
                        onChange={(e) => setNotes({ ...notes, [it.feature]: e.target.value })}
                        className="field fade-in py-2.5 text-[15px]" />
                    )}
                  </fieldset>
                </li>
              );
            })}
          </ul>
        </Section>

        <div className="sticky bottom-[calc(env(safe-area-inset-bottom)+92px)] z-20 md:bottom-6">
          <button onClick={submit} disabled={busy || !count} aria-busy={busy} className="btn btn-primary w-full text-[18px] md:mx-auto md:flex md:max-w-md">
            {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="checkCircle" className="h-5 w-5" />}
            {busy ? "Saving" : count ? `Save ${count} check${count > 1 ? "s" : ""}` : "Pick a result to save"}
          </button>
        </div>
        <p aria-live="polite" className={`text-center text-[15px] font-semibold ${msg?.ok ? "text-ok" : "text-bad"}`}>{msg?.text}</p>
      </div>
    </div>
  );
}
