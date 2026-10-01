"use client";

import { useNow } from "@/lib/hooks";
import { ageText } from "@/lib/store";
import type { FeatureState } from "@/lib/types";
import { SourceTag, StatusBadge, ToneIcon } from "./Status";

const LIVE_FIRST = ["lift", "side_gate", "courtyard_path", "seating"];

/** Widget-style tiles, one per access feature. */
export function LiveBoard({ features, compact = false }: { features: Record<string, FeatureState>; compact?: boolean }) {
  const now = useNow(1000);
  const list = Object.values(features).sort((a, b) => {
    const ia = LIVE_FIRST.indexOf(a.feature);
    const ib = LIVE_FIRST.indexOf(b.feature);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  const shown = compact ? list.filter((f) => LIVE_FIRST.includes(f.feature)) : list;
  return (
    <ul className={`grid gap-3 ${compact ? "sm:grid-cols-2" : "sm:grid-cols-2 xl:grid-cols-3"}`}>
      {shown.map((f) => {
        const flagged = f.blocking ? "ring-2 ring-bad" : f.status === "verify" || f.status === "unknown" ? "ring-2 ring-unsure" : "";
        return (
          <li key={f.feature} className={`card flex flex-col gap-3 p-4 ${flagged}`}>
            <div className="flex items-start gap-3">
              <ToneIcon status={f.status} />
              <div className="min-w-0 flex-1">
                <h3 className="text-[17px] font-semibold leading-tight">{f.label}</h3>
                <div className="mt-1"><SourceTag kind={f.source_kind} age={ageText(f.observed_at, now)} /></div>
              </div>
            </div>
            <div><StatusBadge status={f.status} label={f.status_label} size="sm" /></div>
            {!compact && f.note && <p className="text-[15px] leading-snug text-muted">{f.note}</p>}
            {(f.sensor_offline || f.conflict || f.stale) && (
              <div className="flex flex-wrap gap-1.5">
                {f.sensor_offline && <span className="badge bg-unsure-bg px-2 py-0.5 text-[12px] text-unsure">Sensor silent</span>}
                {f.conflict && <span className="badge bg-unsure-bg px-2 py-0.5 text-[12px] text-unsure">Sources disagree</span>}
                {f.stale && <span className="badge bg-warn-bg px-2 py-0.5 text-[12px] text-warn">May be out of date</span>}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
