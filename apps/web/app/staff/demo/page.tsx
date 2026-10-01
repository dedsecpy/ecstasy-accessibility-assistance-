"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { LiveBoard } from "@/components/LiveBoard";
import { Notice, PageHeader, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { useVenueStream } from "@/lib/hooks";
import type { Health } from "@/lib/types";

export default function DemoPage() {
  const { features, scenario, alerts } = useVenueStream();
  const [scenarios, setScenarios] = useState<Record<string, string>>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const run = async (name: string) => {
    setMsg(null);
    try {
      await api.scenario(name);
      setMsg({ ok: true, text: `Sent "${scenarios[name]}" to the simulators. Watch the board update.` });
    } catch (e) {
      setMsg({ ok: false, text: `Failed: ${(e as Error).message}` });
    }
  };

  const ai = health?.ai;
  const rows: [string, string][] = ai
    ? [
        ["Mode", ai.label],
        ["Embeddings", `${ai.index?.embedder_label || "-"} (${ai.index?.chunks ?? 0} chunks)`],
        ["Answer model", ai.bedrock_enabled ? `${ai.llm_model} on ${ai.provider_label}` : "Not used"],
        ["Planner model", ai.bedrock_enabled ? ai.fast_llm_model : "Not used"],
        ["Rerank", ai.rerank_model || "RRF \u00d7 recency \u00d7 trust (local)"],
        ...(ai.index?.reason && ai.index.reason !== "ok" ? [["Note", ai.index.reason] as [string, string]] : []),
      ]
    : [];

  return (
    <div>
      <PageHeader
        title="Demo console"
        subtitle={<>Sends a scenario over MQTT to the simulated lift sensor (NodeMCU), edge cameras and operations team. Now running: <strong className="font-semibold text-ink">{scenarios[scenario] || scenario}</strong></>}
      />
      <div className="space-y-8">
        <Section id="scenarios" title="Scenarios">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {Object.entries(scenarios).map(([id, label]) => {
              const on = scenario === id;
              return (
                <button key={id} onClick={() => run(id)} aria-pressed={on}
                  className={`card flex min-h-[92px] flex-col justify-between gap-2 p-4 text-left transition-transform active:scale-[0.97] ${on ? "bg-fill text-white" : ""}`}>
                  <span className="text-[16px] font-semibold leading-snug">{label}</span>
                  <span className={`text-[12px] ${on ? "text-white" : "text-muted"}`}>{on ? "Running" : id}</span>
                </button>
              );
            })}
          </div>
          <div aria-live="polite">{msg && <div className="mt-3"><Notice tone={msg.ok ? "ok" : "bad"}>{msg.text}</Notice></div>}</div>
        </Section>

        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <Section id="board" title="Live sources">
            <LiveBoard features={features} compact />
          </Section>

          <div className="space-y-8">
            {alerts.length > 0 && (
              <Section id="al" title="Alerts this session">
                <ul className="list">
                  {alerts.slice(0, 5).map((a) => <li key={a.id} className="px-4 py-3 text-[15px] leading-snug">{a.message}</li>)}
                </ul>
              </Section>
            )}

            <Section id="ai" title="AI configuration">
              <dl className="list">
                {rows.map(([k, v]) => (
                  <div key={k} className="flex items-start justify-between gap-4 px-4 py-3 text-[15px]">
                    <dt className="shrink-0">{k}</dt>
                    <dd className="min-w-0 break-words text-right text-muted">{v}</dd>
                  </div>
                ))}
                {!ai && <div className="row text-muted"><span className="spinner" aria-hidden="true" /> Loading</div>}
                <div>
                  <button onClick={() => api.reindex().then(() => setMsg({ ok: true, text: "Re-index requested; the worker re-embeds changed chunks only." }))}
                    className="row font-semibold text-brand">
                    <Icon name="refresh" className="h-5 w-5" /> Re-index documents
                  </button>
                </div>
              </dl>
            </Section>
          </div>
        </div>
      </div>
    </div>
  );
}
