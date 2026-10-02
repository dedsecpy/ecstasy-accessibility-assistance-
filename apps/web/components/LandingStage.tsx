"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Holds the landing entrance until the wordmark has loaded, so the feathers fade in
 * instead of popping in after their animation has already finished.
 */
export function LandingStage({ className = "", children }: { className?: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const img = ref.current?.querySelector<HTMLImageElement>(".enter-logo");
    const go = () => setReady(true);
    if (!img || img.complete) {
      requestAnimationFrame(go);
      return;
    }
    img.addEventListener("load", go, { once: true });
    img.addEventListener("error", go, { once: true });
    const t = setTimeout(go, 2500);
    return () => {
      clearTimeout(t);
      img.removeEventListener("load", go);
      img.removeEventListener("error", go);
    };
  }, []);

  return (
    <div ref={ref} className={`landing ${ready ? "is-ready" : ""} ${className}`}>
      {children}
    </div>
  );
}
