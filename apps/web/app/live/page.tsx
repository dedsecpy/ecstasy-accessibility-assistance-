"use client";

import { Icon } from "@/components/Icon";
import { LiveBoard } from "@/components/LiveBoard";
import { PageHeader } from "@/components/ui";
import { useVenueStream } from "@/lib/hooks";

export default function LivePage() {
  const { features, connected, changes } = useVenueStream();
  const latest = changes[0];
  return (
    <div>
      <PageHeader
        title="Live at the venue"
        subtitle={<>Fused from the lift sensor, entrance cameras (labels only, no images), staff checks and reports. A silent sensor is never treated as &quot;working&quot;.</>}
        accessory={
          <span className={`badge px-3 py-1.5 text-[15px] ${connected ? "bg-ok-bg text-ok" : "bg-bad-bg text-bad"}`}>
            <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
              {connected && <span className="absolute inline-flex h-full w-full rounded-full bg-current opacity-60 motion-safe:animate-ping" />}
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-current" />
            </span>
            {connected ? "Live" : "Reconnecting"}
          </span>
        }
      />
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {latest ? `${latest.label} is now ${latest.toLabel}` : ""}
      </div>
      {latest && (
        <div key={latest.at} className="fade-in card mb-5 flex items-center gap-3 px-4 py-3 text-[15px]">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-bg text-brand" aria-hidden="true">
            <Icon name="bell" className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            Latest change: <strong className="font-semibold">{latest.label}</strong> is now <strong className="font-semibold">{latest.toLabel}</strong>
          </span>
          <span className="shrink-0 text-[13px] text-muted">{new Date(latest.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
        </div>
      )}
      <LiveBoard features={features} />
    </div>
  );
}
