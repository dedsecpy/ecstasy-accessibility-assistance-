"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { type Citation, CiteChips, CitationSheet } from "@/components/CitationSheet";
import { Icon } from "@/components/Icon";
import { SourceTag, StatusBadge, ToneIcon, VerdictCard } from "@/components/Status";
import { AppLogo, Section } from "@/components/ui";
import { askStream } from "@/lib/api";
import { useVenueStream } from "@/lib/hooks";
import { loadPlan, PHONE_RE, savePlan, type SavedPlan } from "@/lib/store";

function TelText({ text }: { text: string }) {
  const m = text.match(PHONE_RE);
  if (!m) return <>{text}</>;
  const [before, after] = [text.slice(0, m.index), text.slice((m.index || 0) + m[0].length)];
  return (
    <>
      {before}
      <a href={`tel:${m[0].replace(/\s/g, "")}`} className="inline-flex items-center gap-1 font-semibold text-brand underline underline-offset-2">
        <Icon name="phone" className="h-4 w-4" />
        {m[0]}
      </a>
      {after}
    </>
  );
}

export default function AnswerPage() {
  const [plan, setPlan] = useState<SavedPlan | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState<Citation | null>(null);
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [refreshing, setRefreshing] = useState(false);
  const { features } = useVenueStream(plan?.venueId);

  useEffect(() => {
    setPlan(loadPlan());
    setLoaded(true);
  }, []);

  const result = plan?.result;
  const lookup = useMemo(() => {
    const m: Record<string, Citation> = {};
    result?.live.forEach((it) => (m[it.sid] = { kind: "live", item: it }));
    result?.passages.forEach((p) => (m[p.pid] = { kind: "passage", item: p }));
    return m;
  }, [result]);

  // "Your plan changed": a feature this visitor depends on now has a different live status.
  const changed = useMemo(() => {
    if (!result) return [];
    return result.live
      .filter((it) => it.required && features[it.feature] && features[it.feature].status !== it.status)
      .map((it) => ({ label: it.label, from: it.status_label, to: features[it.feature].status_label }));
  }, [result, features]);

  const recheck = async () => {
    if (!plan) return;
    setRefreshing(true);
    try {
      const r = await askStream(plan.request, () => undefined, plan.venueId);
      const next = { ...plan, result: r, savedAt: new Date().toISOString() };
      savePlan(next);
      setPlan(next);
      setChecked({});
    } finally {
      setRefreshing(false);
    }
  };

  if (!loaded) return null;
  if (!result) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
        <AppLogo size={72} />
        <h1 className="large-title mt-2">No answer yet</h1>
        <p className="text-muted">Tell Ecstasy about your visit and it will check the whole route for you, from arrival to your seat.</p>
        <Link href="/plan" className="btn btn-primary mt-2 px-8">Plan a visit</Link>
      </div>
    );
  }
  const a = result.answer;
  const openId = (id: string) => lookup[id] && setOpen(lookup[id]);
  const when = result.visit.visit_at
    ? new Date(result.visit.visit_at).toLocaleString(undefined, { weekday: "long", hour: "2-digit", minute: "2-digit" })
    : null;
  const doneCount = Object.values(checked).filter(Boolean).length;

  return (
    <div>
      <h1 className="sr-only">Your answer</h1>

      {changed.length > 0 && (
        <div role="alert" className="fade-in mb-6 rounded-[22px] bg-unsure-bg p-4 sm:p-5">
          <div className="flex items-start gap-3">
            <Icon name="info" className="mt-0.5 h-6 w-6 shrink-0 text-unsure" />
            <div className="min-w-0 flex-1">
              <p className="text-[17px] font-bold text-unsure">Your plan changed</p>
              <ul className="mt-1 space-y-0.5 text-[15px] text-ink">
                {changed.map((c) => (
                  <li key={c.label}><strong className="font-semibold">{c.label}</strong>: was &quot;{c.from}&quot;, now &quot;{c.to}&quot;</li>
                ))}
              </ul>
              <button onClick={recheck} disabled={refreshing} className="btn btn-sm mt-3 bg-unsure text-bg">
                {refreshing ? <span className="spinner" aria-hidden="true" /> : <Icon name="refresh" className="h-4 w-4" />}
                {refreshing ? "Re-checking" : "Re-check my route"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-8">
          <div className="space-y-4">
            <VerdictCard verdict={a.verdict} headline={a.headline} />
            <div className="flex flex-wrap gap-2 px-1 text-[13px] font-semibold">
              {plan.venueName && (
                <span className="badge bg-card px-3 py-1.5 text-ink"><Icon name="building" className="h-3.5 w-3.5 text-brand" />{plan.venueName}</span>
              )}
              {result.visit.event_name && (
                <span className="badge bg-card px-3 py-1.5 text-ink"><Icon name="calendar" className="h-3.5 w-3.5 text-brand" />{result.visit.event_name}</span>
              )}
              <span className="badge bg-card px-3 py-1.5 text-ink"><Icon name="pin" className="h-3.5 w-3.5 text-brand" />{result.visit.destination || "Any area"}</span>
              {when && <span className="badge bg-card px-3 py-1.5 text-ink"><Icon name="clock" className="h-3.5 w-3.5 text-brand" />{when}</span>}
            </div>
            <p className="px-1 text-[17px] leading-relaxed">{a.summary}</p>
          </div>

          {a.verify.length > 0 && (
            <Section
              id="verify"
              title="Before you travel"
              action={<span className="text-[15px] font-semibold text-muted">{doneCount}/{a.verify.length} done</span>}
            >
              <ul className="list" style={{ ["--inset" as string]: "52px" }}>
                {a.verify.map((v, i) => (
                  <li key={i}>
                    <label className="row cursor-pointer items-start has-[input:focus-visible]:outline-3 has-[input:focus-visible]:outline-brand has-[input:focus-visible]:-outline-offset-3">
                      <input type="checkbox" checked={!!checked[i]} onChange={() => setChecked({ ...checked, [i]: !checked[i] })} className="peer sr-only" />
                      <Icon name="circle" className="mt-px h-6 w-6 shrink-0 text-field peer-checked:hidden" />
                      <Icon name="checkCircle" stroke={2.2} className="mt-px hidden h-6 w-6 shrink-0 text-brand peer-checked:block" />
                      <span className={`text-[16px] leading-snug ${checked[i] ? "text-muted line-through" : ""}`}><TelText text={v} /></span>
                    </label>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {a.route.length > 0 && (
            <Section id="route" title="Your route">
              <ol className="card p-5 sm:p-6">
                {a.route.map((s, i) => (
                  <li key={i} className="relative flex gap-4 pb-6 last:pb-0">
                    {i < a.route.length - 1 && <span aria-hidden="true" className="absolute left-[15px] top-9 bottom-1 w-[2px] rounded-full bg-line" />}
                    <span className="relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fill text-[15px] font-bold text-white" aria-hidden="true">{i + 1}</span>
                    <p className="min-w-0 pt-1 text-[16px] leading-snug">
                      <span className="sr-only">Step {i + 1}: </span>
                      {s.text}
                      <CiteChips ids={s.citations} onOpen={openId} />
                    </p>
                  </li>
                ))}
              </ol>
            </Section>
          )}

          {a.warnings.length > 0 && (
            <Section id="warn" title="Things to know">
              <ul className="list" style={{ ["--inset" as string]: "56px" }}>
                {a.warnings.map((w, i) => (
                  <li key={i} className="row items-start">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-warn-bg text-warn" aria-hidden="true">
                      <Icon name="alert" stroke={2.2} className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 pt-1 text-[16px] leading-snug">{w.text}<CiteChips ids={w.citations} onOpen={openId} /></span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {a.discrepancies.length > 0 && (
            <Section id="disc" title="Where the public listing is wrong">
              <ul className="list" style={{ ["--inset" as string]: "56px" }}>
                {a.discrepancies.map((d, i) => (
                  <li key={i} className="row items-start">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-bad-bg text-bad" aria-hidden="true">
                      <Icon name="close" stroke={2.4} className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 pt-1 text-[16px] leading-snug">{d.text}<CiteChips ids={d.citations} onOpen={openId} /></span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        <aside className="space-y-8 lg:sticky lg:top-12">
          <Section id="live" title="Live status" footer="Tap an item to see the evidence behind it.">
            <ul className="list" style={{ ["--inset" as string]: "64px" }}>
              {result.live.filter((it) => it.required).map((it) => (
                <li key={it.sid}>
                  <button onClick={() => setOpen({ kind: "live", item: it })} className="row">
                    <ToneIcon status={it.status} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[16px] font-semibold leading-tight">{it.label}</span>
                      <span className="mt-1 block"><StatusBadge status={it.status} label={it.status_label} size="sm" /></span>
                      <span className="mt-1 block"><SourceTag kind={it.source_kind} age={it.age_text} /></span>
                    </span>
                    <span className="text-[13px] font-semibold text-muted">{it.sid}</span>
                    <Icon name="chevron" className="h-4 w-4 shrink-0 text-muted" />
                  </button>
                </li>
              ))}
            </ul>
          </Section>

          <details className="card group overflow-hidden">
            <summary className="row cursor-pointer list-none justify-between font-semibold [&::-webkit-details-marker]:hidden">
              <span className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-brand-bg text-brand" aria-hidden="true">
                  <Icon name="sparkle" className="h-4 w-4" />
                </span>
                How this answer was made
              </span>
              <Icon name="chevron" className="h-4 w-4 text-muted transition-transform group-open:rotate-90" />
            </summary>
            <dl className="space-y-3 px-4 pb-4 text-[15px]">
              {[
                ["Answer", result.mode === "llm"
                  ? "Written by Ecstasy AI from the evidence, then checked against the safety rules"
                  : "Built by the Ecstasy rule engine from the evidence"],
                ["Evidence", `${result.passages.length} venue records, ${result.live.length} live status items`],
                ["Safety checks", result.validation.fixes.length ? result.validation.fixes.join("; ") : "Passed with no overrides"],
                ["Time", `${(result.latency_ms / 1000).toFixed(1)} s, ${new Date(result.generated_at).toLocaleTimeString()}`],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[13px] font-semibold uppercase tracking-wide text-muted">{k}</dt>
                  <dd className="mt-0.5 break-words">{v}</dd>
                </div>
              ))}
            </dl>
            {result.ai.error && (
              <p className="mx-4 mb-4 rounded-[14px] bg-warn-bg px-3 py-2 text-[14px] text-warn">
                The AI writer was unavailable, so the rule engine wrote this answer. It uses the same evidence and safety checks.
              </p>
            )}
          </details>

          <div className="grid grid-cols-2 gap-3">
            <button onClick={recheck} disabled={refreshing} className="btn btn-tinted">
              {refreshing ? <span className="spinner" aria-hidden="true" /> : <Icon name="refresh" className="h-4 w-4" />}
              {refreshing ? "Checking" : "Re-check"}
            </button>
            <Link href="/plan" className="btn btn-primary min-h-[44px]">Change plan</Link>
          </div>
        </aside>
      </div>

      <CitationSheet citation={open} onClose={() => setOpen(null)} />
    </div>
  );
}
