"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useVenueStream } from "@/lib/hooks";
import type { Alert } from "@/lib/types";

const SEV: Record<string, { cls: string; icon: IconName; word: string }> = {
  high: { cls: "bg-bad-bg text-bad", icon: "stop", word: "Urgent" },
  medium: { cls: "bg-warn-bg text-warn", icon: "alert", word: "Check" },
  info: { cls: "bg-ok-bg text-ok", icon: "check", word: "Resolved" },
};

export default function AlertsPage() {
  const [history, setHistory] = useState<Alert[]>([]);
  const { alerts: live } = useVenueStream();

  useEffect(() => {
    api.alerts().then(setHistory).catch(() => undefined);
  }, []);

  const all = useMemo(() => {
    const seen = new Set<number>();
    return [...live, ...history].filter((a) => (seen.has(a.id) ? false : (seen.add(a.id), true)));
  }, [live, history]);

  const ack = async (id: number) => {
    await api.ack(id);
    setHistory((h) => h.map((a) => (a.id === id ? { ...a, acked: true } : a)));
  };

  const open = all.filter((a) => !a.acked && a.severity !== "info").length;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Alerts"
        subtitle="Raised automatically when a feature becomes blocking, sources disagree, or a sensor goes silent."
        accessory={
          <span className={`badge px-3 py-1.5 text-[15px] ${open ? "bg-bad-bg text-bad" : "bg-ok-bg text-ok"}`}>
            <Icon name={open ? "bell" : "check"} className="h-4 w-4" />
            {open ? `${open} open` : "All clear"}
          </span>
        }
      />
      <ul className="list" aria-live="polite" style={{ ["--inset" as string]: "68px" }}>
        {all.map((a) => {
          const s = SEV[a.severity] || SEV.medium;
          const pending = !a.acked && a.severity !== "info";
          return (
            <li key={a.id} className={`row items-start py-4 ${a.acked ? "opacity-60" : ""}`}>
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${s.cls}`} aria-hidden="true">
                <Icon name={s.icon} stroke={2.2} className="h-[18px] w-[18px]" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-[15px] font-semibold capitalize">
                    {s.word} <span className="font-normal text-muted">&middot; {a.kind.replace(/_/g, " ")}</span>
                  </p>
                  <time className="shrink-0 text-[13px] text-muted" dateTime={a.created_at}>
                    {new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </time>
                </div>
                <p className="mt-0.5 text-[16px] leading-snug">{a.message}</p>
                {pending && (
                  <button onClick={() => ack(a.id)} className="btn btn-tinted btn-sm mt-2.5">
                    Acknowledge
                  </button>
                )}
                {a.acked && <p className="mt-1 text-[13px] text-muted">Acknowledged</p>}
              </div>
            </li>
          );
        })}
        {!all.length && (
          <li className="row justify-center py-10 text-muted">
            <Icon name="checkCircle" className="h-5 w-5" /> No alerts yet.
          </li>
        )}
      </ul>
    </div>
  );
}
