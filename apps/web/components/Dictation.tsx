"use client";

import { Icon } from "@/components/Icon";
import type { Speech } from "@/lib/hooks";

function clock(s: number) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function MicButton({ speech, label }: { speech: Speech; label: string }) {
  if (!speech.supported) return null;
  const { listening, transcribing } = speech;
  return (
    <button
      type="button"
      onClick={speech.toggle}
      disabled={transcribing}
      aria-pressed={listening}
      aria-label={listening ? "Stop recording" : transcribing ? "Turning speech into text" : label}
      title={listening ? "Stop recording" : label}
      className={`tap flex shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-80 ${
        listening ? "bg-bad-bg text-bad motion-safe:animate-pulse" : "bg-brand-bg text-brand"
      }`}
    >
      {transcribing ? (
        <span className="spinner" aria-hidden="true" />
      ) : (
        <Icon name={listening ? "square" : "mic"} className="h-5 w-5" />
      )}
    </button>
  );
}

export function DictationStatus({ speech }: { speech: Speech }) {
  if (!speech.supported) return null;
  const { listening, transcribing, error, mode, seconds } = speech;
  return (
    <p aria-live="polite" className="min-h-0 text-[14px] empty:hidden">
      {listening && (
        <span className="mt-2 flex items-center gap-2 text-muted">
          <span className="h-2 w-2 rounded-full bg-bad motion-safe:animate-pulse" aria-hidden="true" />
          Listening{mode === "deepgram" ? ` ${clock(seconds)}` : ""}. Tap the button again when you have finished.
        </span>
      )}
      {transcribing && (
        <span className="mt-2 flex items-center gap-2 text-muted">Turning your speech into text&hellip;</span>
      )}
      {!listening && !transcribing && error && <span className="mt-2 block text-bad">{error}</span>}
    </p>
  );
}
