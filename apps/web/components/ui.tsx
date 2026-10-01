"use client";

import { Icon } from "./Icon";

export function AppLogo({ size = 32 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex shrink-0 items-center justify-center text-white shadow-[0_4px_12px_-4px_rgba(0,102,204,0.6)]"
      style={{ width: size, height: size, borderRadius: size * 0.28, background: "linear-gradient(180deg,#3d8bff 0%,#0058cc 100%)" }}
    >
      <Icon name="angel" className="h-[70%] w-[70%]" stroke={2} />
    </span>
  );
}

export function PageHeader({ title, subtitle, accessory }: { title: string; subtitle?: React.ReactNode; accessory?: React.ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-4 gap-y-3 md:mb-8">
      <div className="min-w-0">
        <h1 className="large-title">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-[17px] leading-snug text-muted">{subtitle}</p>}
      </div>
      {accessory && <div className="shrink-0">{accessory}</div>}
    </header>
  );
}

export function Section({
  id, title, footer, action, children, className = "",
}: { id?: string; title?: string; footer?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  const hid = id && title ? `${id}-h` : undefined;
  return (
    <section aria-labelledby={hid} className={`space-y-2.5 ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-2 px-1">
          <h2 id={hid} className="section-title">{title}</h2>
          {action}
        </div>
      )}
      {children}
      {footer && <p className="section-footer">{footer}</p>}
    </section>
  );
}

/** A full-width row that behaves as a switch; the visual track is decorative. */
export function SwitchRow({ checked, onChange, label, detail }: { checked: boolean; onChange: (v: boolean) => void; label: string; detail?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="row justify-between">
      <span className="min-w-0">
        <span className="block">{label}</span>
        {detail && <span className="block text-[15px] text-muted">{detail}</span>}
      </span>
      <span className="switch-track" aria-hidden="true" />
    </button>
  );
}

/** A radio row with a trailing checkmark, like an iOS Settings choice list. */
export function ChoiceRow({
  name, value, checked, onChange, title, detail, leading,
}: { name: string; value: string; checked: boolean; onChange: () => void; title: React.ReactNode; detail?: React.ReactNode; leading?: React.ReactNode }) {
  return (
    <label className="row cursor-pointer has-[input:focus-visible]:outline-3 has-[input:focus-visible]:outline-brand has-[input:focus-visible]:-outline-offset-3">
      <input type="radio" name={name} value={value} checked={checked} onChange={onChange} className="peer sr-only" />
      {leading}
      <span className="min-w-0 flex-1">
        <span className={`block ${checked ? "font-semibold" : ""}`}>{title}</span>
        {detail && <span className="block text-[15px] leading-snug text-muted">{detail}</span>}
      </span>
      <Icon name="check" stroke={2.6} className="invisible h-5 w-5 shrink-0 text-brand peer-checked:visible" />
    </label>
  );
}

export function Segmented<T extends string>({
  label, value, options, onChange,
}: { label: string; value: T | undefined; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="segmented">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Notice({ tone, children }: { tone: "bad" | "warn" | "ok" | "unsure"; children: React.ReactNode }) {
  const cls = { bad: "bg-bad-bg text-bad", warn: "bg-warn-bg text-warn", ok: "bg-ok-bg text-ok", unsure: "bg-unsure-bg text-unsure" }[tone];
  const icon = { bad: "stop", warn: "alert", ok: "checkCircle", unsure: "info" }[tone] as "stop" | "alert" | "checkCircle" | "info";
  return (
    <div role={tone === "bad" ? "alert" : undefined} className={`flex items-start gap-3 rounded-[18px] px-4 py-3 text-[15px] font-semibold ${cls}`}>
      <Icon name={icon} className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
