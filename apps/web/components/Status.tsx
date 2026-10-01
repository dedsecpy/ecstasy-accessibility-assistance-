import { Icon, type IconName } from "./Icon";

type Tone = "ok" | "warn" | "bad" | "unsure";

export function toneFor(status: string): Tone {
  if (status === "ok" || status === "locked_on_request") return "ok";
  if (status === "degraded") return "warn";
  if (status === "verify" || status === "unknown") return "unsure";
  return "bad";
}

export const TONE: Record<Tone, { cls: string; text: string; icon: IconName; word: string }> = {
  ok: { cls: "bg-ok-bg text-ok", text: "text-ok", icon: "check", word: "OK" },
  warn: { cls: "bg-warn-bg text-warn", text: "text-warn", icon: "alert", word: "Limited" },
  bad: { cls: "bg-bad-bg text-bad", text: "text-bad", icon: "stop", word: "Blocked" },
  unsure: { cls: "bg-unsure-bg text-unsure", text: "text-unsure", icon: "help", word: "Unconfirmed" },
};

/** Status is always icon + words, never colour alone. */
export function StatusBadge({ status, label, size = "md" }: { status: string; label: string; size?: "sm" | "md" }) {
  const t = TONE[toneFor(status)];
  return (
    <span className={`badge ${t.cls} ${size === "sm" ? "px-2.5 py-1 text-[13px]" : "px-3 py-1.5 text-[15px]"}`}>
      <Icon name={t.icon} stroke={2.4} className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      {label}
    </span>
  );
}

/** Round tinted icon used as the leading element of list rows and tiles. */
export function ToneIcon({ status, size = 36 }: { status: string; size?: number }) {
  const t = TONE[toneFor(status)];
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center rounded-full ${t.cls}`} style={{ width: size, height: size }}>
      <Icon name={t.icon} stroke={2.4} className="h-[50%] w-[50%]" />
    </span>
  );
}

const SOURCE_ICON: Record<string, IconName> = {
  sensor: "sensor",
  cctv: "camera",
  staff: "user",
  maintenance_log: "wrench",
  report: "message",
  audit: "clipboard",
  policy: "file",
};

const SOURCE_LABEL: Record<string, string> = {
  sensor: "Lift sensor",
  cctv: "Camera",
  staff: "Staff check",
  maintenance_log: "Maintenance log",
  report: "Visitor report",
  audit: "Access audit",
  policy: "Venue policy",
};

export function SourceTag({ kind, age }: { kind: string; age?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
      <Icon name={SOURCE_ICON[kind] || "file"} className="h-3.5 w-3.5" />
      <span>
        {SOURCE_LABEL[kind] || kind}
        {age ? ` \u00b7 ${age}` : ""}
      </span>
    </span>
  );
}

const VERDICT: Record<string, { tone: Tone; icon: IconName; word: string; blurb: string }> = {
  go: { tone: "ok", icon: "check", word: "Go", blurb: "Your route works today." },
  caution: { tone: "warn", icon: "alert", word: "Caution", blurb: "Workable, with things to check first." },
  no_go: { tone: "bad", icon: "stop", word: "No-Go", blurb: "Don't travel yet." },
};

export function VerdictCard({ verdict, headline }: { verdict: string; headline: string }) {
  const v = VERDICT[verdict] || VERDICT.caution;
  const t = TONE[v.tone];
  return (
    <section aria-labelledby="verdict-h" className={`fade-in relative overflow-hidden rounded-[28px] p-6 sm:p-8 ${t.cls}`}>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full opacity-[0.12] blur-3xl"
        style={{ background: "currentColor" }}
      />
      <div className="relative flex items-center gap-4">
        <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-card ${t.text} shadow-sm`} aria-hidden="true">
          <Icon name={v.icon} stroke={2.6} className="h-7 w-7" />
        </span>
        <div>
          <h2 id="verdict-h" className="text-[34px] font-bold leading-none tracking-tight">{v.word}</h2>
          <p className="mt-1 text-[15px] font-semibold">{v.blurb}</p>
        </div>
      </div>
      <p className="relative mt-5 text-[22px] font-semibold leading-[1.25] tracking-tight text-ink sm:text-[24px]">{headline}</p>
    </section>
  );
}
