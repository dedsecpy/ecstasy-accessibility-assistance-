"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiBase, VENUE_ID } from "./api";
import type { Alert, FeatureState } from "./types";

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export interface StatusChange {
  feature: string;
  label: string;
  from: string | null;
  to: string;
  toLabel: string;
  at: number;
}

/** Live venue board over SSE: snapshot first, then incremental status / alert / scenario events. */
export function useVenueStream(venueId = VENUE_ID) {
  const [features, setFeatures] = useState<Record<string, FeatureState>>({});
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [scenario, setScenario] = useState<string>("normal");
  const [connected, setConnected] = useState(false);
  const [changes, setChanges] = useState<StatusChange[]>([]);
  const featuresRef = useRef(features);
  featuresRef.current = features;

  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;

    const refetch = () =>
      api.status(venueId).then((s) => {
        const map: Record<string, FeatureState> = {};
        s.features.forEach((f) => (map[f.feature] = f));
        setFeatures(map);
        setScenario(s.scenario);
      }).catch(() => undefined);

    const open = () => {
      es = new EventSource(`${apiBase()}/api/venues/${venueId}/stream`);
      es.onopen = () => setConnected(true);
      es.onerror = () => setConnected(false);
      es.addEventListener("snapshot", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        const map: Record<string, FeatureState> = {};
        (d.features as FeatureState[]).forEach((f) => (map[f.feature] = f));
        setFeatures(map);
        setScenario(d.scenario);
        setConnected(true);
      });
      es.addEventListener("status", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        if (!d.state) {
          refetch();
          return;
        }
        const st = d.state as FeatureState;
        const prev = featuresRef.current[st.feature];
        if (!prev || prev.status !== st.status) {
          setChanges((c) => [
            { feature: st.feature, label: st.label, from: prev?.status ?? null, to: st.status, toLabel: st.status_label, at: Date.now() },
            ...c,
          ].slice(0, 20));
        }
        setFeatures((f) => ({ ...f, [st.feature]: st }));
      });
      es.addEventListener("alert", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        if (d.alert) setAlerts((a) => [d.alert as Alert, ...a].slice(0, 100));
      });
      es.addEventListener("scenario", (e) => {
        const d = JSON.parse((e as MessageEvent).data);
        setScenario(d.scenario);
      });
    };

    if (!closed) open();
    return () => {
      closed = true;
      es?.close();
    };
  }, [venueId]);

  return { features, alerts, scenario, connected, changes };
}

export function useSpeech(onText: (t: string) => void) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(false);
  const recRef = useRef<any>(null);

  useEffect(() => {
    const w = window as any;
    setSupported(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, []);

  const toggle = () => {
    const w = window as any;
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) return;
    if (listening && recRef.current) {
      recRef.current.stop();
      return;
    }
    const rec = new SR();
    rec.lang = navigator.language || "en-GB";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (ev: any) => onText(ev.results[0][0].transcript as string);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  return { listening, supported, toggle };
}
