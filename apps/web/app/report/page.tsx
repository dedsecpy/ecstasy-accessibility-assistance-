"use client";

import { useState } from "react";
import { DictationStatus, MicButton } from "@/components/Dictation";
import { Icon } from "@/components/Icon";
import { StatusBadge, ToneIcon } from "@/components/Status";
import { Notice, PageHeader, Section } from "@/components/ui";
import { api, type ReportStatus } from "@/lib/api";
import { useSpeech } from "@/lib/hooks";

export default function ReportPage() {
  const [text, setText] = useState("");
  const [needs, setNeeds] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ReportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const speech = useSpeech((t) => setText((x) => (x ? `${x} ${t}` : t)));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim().length < 3) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const { id } = await api.report({ text, reporter: "visitor", needs });
      for (let i = 0; i < 30; i++) {
        const s = await api.reportStatus(id);
        if (s.status === "done" || s.status === "error") {
          setResult(s);
          break;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      setText("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl">
      <PageHeader
        title="Tell us what you found"
        subtitle="Was the lift working? Was the gate answered? Was there somewhere to sit? Your report updates live status for the next visitor and goes to venue staff."
      />
      <div className="space-y-8">
        <Section id="what" title="What happened?">
          <div className="card p-3">
            <label htmlFor="report" className="sr-only">What happened?</label>
            <div className="flex items-start gap-2">
              <textarea id="report" required minLength={3} rows={5} value={text} onChange={(e) => setText(e.target.value)}
                className="field min-h-[140px] resize-none" placeholder="e.g. The side gate was locked and nobody answered the intercom at 18:30." />
              <MicButton speech={speech} label="Dictate your report" />
            </div>
            <DictationStatus speech={speech} />
          </div>
        </Section>

        <Section id="needs" title="Your access needs" footer="Optional. Helps staff understand who the issue affects.">
          <div className="card p-3">
            <label htmlFor="needs" className="sr-only">Your access needs (optional)</label>
            <input id="needs" value={needs} onChange={(e) => setNeeds(e.target.value)} className="field" placeholder="e.g. manual wheelchair" />
          </div>
        </Section>

        <button type="submit" disabled={busy} aria-busy={busy} className="btn btn-primary w-full text-[18px]">
          {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="send" className="h-5 w-5" />}
          {busy ? "Sending and reading your report" : "Send report"}
        </button>

        <div aria-live="polite" className="space-y-3">
          {error && <Notice tone="bad">{error}</Notice>}
          {result?.status === "done" && result.extraction && (
            <section aria-labelledby="thanks-h" className="fade-in space-y-3">
              <Notice tone="ok"><span id="thanks-h">Thank you. Here is what Ecstasy understood.</span></Notice>
              {result.extraction.facts.length === 0 ? (
                <p className="card px-4 py-3 text-[15px]">No specific access feature was recognised; your report is saved for staff.</p>
              ) : (
                <ul className="list" style={{ ["--inset" as string]: "64px" }}>
                  {result.extraction.facts.map((f, i) => (
                    <li key={i} className="row items-start">
                      <ToneIcon status={f.status} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold capitalize">{f.feature.replace(/_/g, " ")}</span>
                          <StatusBadge status={f.status} label={f.status.replace(/_/g, " ")} size="sm" />
                        </div>
                        <p className="mt-1 text-[15px] text-muted">{f.note}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <p className="section-footer">Read by: {result.extraction.mode === "llm" ? "AI model" : "rule-based extractor (local fallback)"}</p>
            </section>
          )}
        </div>
      </div>
    </form>
  );
}
