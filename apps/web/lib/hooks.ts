"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiBase, currentVenueId, VENUE_EVENT } from "./api";
import type { Alert, FeatureState } from "./types";

/** The selected venue id; follows changes made on other pages and in other tabs. */
export function useVenueId(): string {
  const [id, setId] = useState(currentVenueId);
  useEffect(() => {
    const sync = () => setId(currentVenueId());
    sync();
    window.addEventListener(VENUE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(VENUE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return id;
}

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
export function useVenueStream(fixedVenueId?: string) {
  const selected = useVenueId();
  const venueId = fixedVenueId || selected;
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
    setFeatures({});
    setAlerts([]);
    setChanges([]);

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

type SpeechMode = "deepgram" | "browser" | null;
type SpeechState = "idle" | "listening" | "transcribing";

const RECORDER_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

function micError(e: unknown): string {
  const name = (e as { name?: string })?.name;
  if (name === "NotAllowedError" || name === "SecurityError")
    return "Microphone access is blocked. Allow it in your browser's site settings, then try again.";
  if (name === "NotFoundError") return "No microphone was found on this device.";
  if (name === "NotReadableError") return "The microphone is being used by another app.";
  return "Could not start the microphone.";
}

/**
 * Dictation. Records with MediaRecorder and transcribes on the server through Deepgram when the API has a key;
 * otherwise falls back to the browser's own speech recognition where it exists (Chrome, Edge).
 */
export function useSpeech(onText: (t: string) => void) {
  const [mode, setMode] = useState<SpeechMode>(null);
  const [state, setState] = useState<SpeechState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;
  const recRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const maxSecondsRef = useRef(60);
  const discardRef = useRef(false);

  const release = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  useEffect(() => {
    const w = window as any;
    const builtIn = Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
    const canRecord = Boolean(navigator.mediaDevices?.getUserMedia) && typeof w.MediaRecorder !== "undefined";
    setMode(builtIn ? "browser" : null);
    let cancelled = false;
    if (canRecord) {
      api.sttStatus().then((s) => {
        if (cancelled || !s.enabled) return;
        maxSecondsRef.current = s.max_seconds || 60;
        setMode("deepgram");
      }).catch(() => undefined);
    }
    return () => {
      cancelled = true;
      discardRef.current = true;
      try {
        recRef.current?.stop();
      } catch {
        /* already stopped */
      }
      release();
    };
  }, []);

  const startDeepgram = async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      setError(micError(e));
      return;
    }
    const w = window as any;
    const type = RECORDER_TYPES.find((t) => w.MediaRecorder.isTypeSupported?.(t));
    const rec: MediaRecorder = new w.MediaRecorder(stream, type ? { mimeType: type } : undefined);
    const chunks: Blob[] = [];
    streamRef.current = stream;
    discardRef.current = false;
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onstop = async () => {
      release();
      recRef.current = null;
      if (discardRef.current) return;
      const blob = new Blob(chunks, { type: rec.mimeType || type || "audio/webm" });
      if (blob.size < 1200) {
        setState("idle");
        setError("I didn't catch that. Tap the microphone and speak.");
        return;
      }
      setState("transcribing");
      try {
        const r = await api.transcribe(blob, navigator.language);
        if (r.text) onTextRef.current(r.text);
        else setError("No speech was heard. Please try again a little closer to the microphone.");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setState("idle");
      }
    };
    recRef.current = rec;
    rec.start(250);
    setSeconds(0);
    setState("listening");
    const started = Date.now();
    timerRef.current = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      setSeconds(s);
      if (s >= maxSecondsRef.current && rec.state === "recording") rec.stop();
    }, 250);
  };

  const startBrowser = () => {
    const w = window as any;
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = navigator.language || "en-GB";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (ev: any) => onTextRef.current(ev.results[0][0].transcript as string);
    rec.onend = () => setState("idle");
    rec.onerror = (ev: any) => {
      if (ev?.error === "not-allowed") setError(micError({ name: "NotAllowedError" }));
      else if (ev?.error !== "no-speech" && ev?.error !== "aborted") setError("Speech recognition stopped unexpectedly.");
      setState("idle");
    };
    recRef.current = rec;
    setSeconds(0);
    setState("listening");
    rec.start();
  };

  const toggle = () => {
    if (state === "transcribing") return;
    if (state === "listening") {
      recRef.current?.stop();
      return;
    }
    setError(null);
    if (mode === "deepgram") void startDeepgram();
    else if (mode === "browser") startBrowser();
  };

  return {
    supported: mode !== null,
    mode,
    listening: state === "listening",
    transcribing: state === "transcribing",
    seconds,
    error,
    toggle,
  };
}

export type Speech = ReturnType<typeof useSpeech>;
