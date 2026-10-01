"use client";

import { useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { Notice, PageHeader, Section } from "@/components/ui";
import { api, type ListingHealth } from "@/lib/api";

const VERDICT: Record<string, { cls: string; icon: IconName; word: string }> = {
  supported: { cls: "bg-ok-bg text-ok", icon: "check", word: "Supported" },
  qualified: { cls: "bg-warn-bg text-warn", icon: "alert", word: "Needs qualifying" },
  contradicted: { cls: "bg-bad-bg text-bad", icon: "stop", word: "Contradicted" },
  unverified: { cls: "bg-unsure-bg text-unsure", icon: "help", word: "Unverified" },
};

export default function ListingPage() {
  const [data, setData] = useState<ListingHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api.listingHealth().then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const copy = async () => {
    if (!data) return;
    await navigator.clipboard?.writeText(data.draft_listing);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const counts = data?.claims.reduce<Record<string, number>>((m, c) => ({ ...m, [c.verdict]: (m[c.verdict] || 0) + 1 }), {});

  return (
    <div>
      <PageHeader
        title="Listing health"
        subtitle={data
          ? `The public listing was last updated ${data.listing_updated}${data.listing_age_days != null ? ` (${data.listing_age_days} days ago)` : ""}. Each claim is checked against live, fused status.`
          : "Audits the venue's public accessibility listing against live status."}
        accessory={
          <button onClick={load} disabled={loading} className="btn btn-tinted btn-sm">
            {loading ? <span className="spinner" aria-hidden="true" /> : <Icon name="refresh" className="h-4 w-4" />}
            Refresh
          </button>
        }
      />
      <p aria-live="polite" className="sr-only">{loading ? "Auditing the public listing against live status" : ""}</p>
      {error && <div className="mb-6"><Notice tone="bad">{error}</Notice></div>}
      {!data && loading && (
        <div className="card flex items-center gap-3 p-5 text-muted"><span className="spinner" aria-hidden="true" /> Auditing the public listing against live status</div>
      )}
      {data && (
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-8">
            {counts && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {Object.entries(VERDICT).map(([k, v]) => (
                  <div key={k} className="card p-4">
                    <span className={`flex h-8 w-8 items-center justify-center rounded-full ${v.cls}`} aria-hidden="true">
                      <Icon name={v.icon} stroke={2.2} className="h-4 w-4" />
                    </span>
                    <p className="mt-3 text-[28px] font-bold leading-none tracking-tight">{counts[k] || 0}</p>
                    <p className="mt-1 text-[13px] font-semibold text-muted">{v.word}</p>
                  </div>
                ))}
              </div>
            )}

            <Section id="claims" title="Claims">
              <ul className="list">
                {data.claims.map((c) => {
                  const v = VERDICT[c.verdict];
                  return (
                    <li key={c.claim} className="px-4 py-3.5">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <span className="text-[16px] font-semibold">&ldquo;{c.claim}&rdquo;</span>
                        <span className={`badge px-2.5 py-1 text-[13px] ${v.cls}`}>
                          <Icon name={v.icon} stroke={2.4} className="h-3.5 w-3.5" /> {v.word}
                        </span>
                      </div>
                      {c.reasons.length > 0 && (
                        <ul className="mt-1.5 space-y-1 text-[15px] leading-snug text-muted">
                          {c.reasons.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Section>

            {data.affected_events.length > 0 && (
              <Section id="ev" title="Upcoming events at risk">
                <ul className="list" style={{ ["--inset" as string]: "64px" }}>
                  {data.affected_events.map((e) => (
                    <li key={e.id} className="row items-start">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-warn-bg text-warn" aria-hidden="true">
                        <Icon name="calendar" className="h-5 w-5" />
                      </span>
                      <div className="min-w-0">
                        <p className="font-semibold">{e.name}</p>
                        <p className="text-[15px] text-muted">
                          {new Date(e.start).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} &middot; {e.location}
                        </p>
                        <p className="mt-1 text-[15px]">{e.issues.join("; ")}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <Section id="actions" title="Staff actions">
              <ol className="list" style={{ ["--inset" as string]: "56px" }}>
                {data.staff_actions.map((a, i) => (
                  <li key={i} className="row items-start">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-bg text-[13px] font-bold text-brand" aria-hidden="true">{i + 1}</span>
                    <span className="pt-0.5 text-[16px] leading-snug">{a}</span>
                  </li>
                ))}
              </ol>
            </Section>
          </div>

          <Section
            id="draft"
            title="Drafted honest listing"
            className="lg:sticky lg:top-12"
            footer={data.mode === "llm" ? `Written by ${data.ai_label} from live status.` : "Template draft (local fallback)."}
            action={
              <button onClick={copy} className="btn btn-tinted btn-sm" aria-live="polite">
                <Icon name={copied ? "check" : "copy"} className="h-4 w-4" />
                {copied ? "Copied" : "Copy"}
              </button>
            }
          >
            <pre className="card max-h-[70dvh] overflow-y-auto whitespace-pre-wrap p-5 font-sans text-[15px] leading-relaxed">{data.draft_listing}</pre>
          </Section>
        </div>
      )}
    </div>
  );
}
