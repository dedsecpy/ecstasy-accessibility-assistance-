"use client";

import { useEffect, useRef } from "react";

const SELECTOR = ".enter, .enter-logo";

/**
 * Starts the landing entrance once the wordmark has loaded, so the feathers fade in instead of
 * popping in after their animation has finished. The inline script starts it during HTML parsing
 * (before hydration, which is slow on phones); the effect covers client-side navigation, where
 * inline scripts do not run. Replays when a phone restores the tab from memory.
 */
const BOOT = `(function(){var s=document.currentScript.parentElement,i=s.querySelector(".enter-logo");function go(){s.classList.add("is-ready")}if(!i||i.complete)go();else{i.addEventListener("load",go);i.addEventListener("error",go);setTimeout(go,2500)}})();`;

export function LandingStage({ className = "", children }: { className?: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stage = ref.current;
    if (!stage) return;
    const go = () => stage.classList.add("is-ready");
    const img = stage.querySelector<HTMLImageElement>(".enter-logo");
    let t: ReturnType<typeof setTimeout> | undefined;
    if (!img || img.complete) go();
    else {
      img.addEventListener("load", go, { once: true });
      img.addEventListener("error", go, { once: true });
      t = setTimeout(go, 2500);
    }

    const replay = (e: PageTransitionEvent) => {
      if (!e.persisted) return;
      stage.querySelectorAll<HTMLElement>(SELECTOR).forEach((el) => {
        el.style.animation = "none";
        void el.offsetWidth;
        el.style.animation = "";
      });
    };
    window.addEventListener("pageshow", replay);
    return () => {
      clearTimeout(t);
      img?.removeEventListener("load", go);
      img?.removeEventListener("error", go);
      window.removeEventListener("pageshow", replay);
    };
  }, []);

  return (
    <div ref={ref} className={`landing ${className}`} suppressHydrationWarning>
      <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      {children}
    </div>
  );
}
