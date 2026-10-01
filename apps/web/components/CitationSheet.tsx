"use client";

import { useEffect, useRef } from "react";
import type { LiveItem, PassageT } from "@/lib/types";
import { Icon } from "./Icon";
import { SourceTag, StatusBadge } from "./Status";

export type Citation = { kind: "live"; item: LiveItem } | { kind: "passage"; item: PassageT };

/** iOS-style sheet built on <dialog>: focus is trapped and Escape closes it. */
export function CitationSheet({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (citation && !d.open) d.showModal();
    if (!citation && d.open) d.close();
  }, [citation]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="cite-title"
      className="sheet"
    >
      {citation && (
        <div className="max-h-[88dvh] overflow-y-auto px-5 pb-[calc(env(safe-area-inset-bottom)+24px)] pt-2 md:max-h-[80dvh] md:px-7 md:pb-7 md:pt-5">
          <div className="mx-auto mb-3 h-[5px] w-9 rounded-full bg-line md:hidden" aria-hidden="true" />
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13px] font-semibold uppercase tracking-wide text-muted">
                {citation.kind === "live" ? `Evidence ${citation.item.sid} \u00b7 live status` : `Evidence ${citation.item.pid} \u00b7 venue record`}
              </p>
              <h2 id="cite-title" className="mt-0.5 text-[22px] font-bold leading-tight tracking-tight">
                {citation.kind === "live" ? citation.item.label : citation.item.doc_title}
              </h2>
            </div>
            <button onClick={onClose} className="tap -mr-2 -mt-1 inline-flex items-center justify-center" aria-label="Close">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-card2 text-muted">
                <Icon name="close" stroke={2.4} className="h-4 w-4" />
              </span>
            </button>
          </div>
          {citation.kind === "live" ? (
            <div className="space-y-3">
              <StatusBadge status={citation.item.status} label={citation.item.status_label} />
              <p className="text-[17px] leading-relaxed">{citation.item.note}</p>
              <SourceTag kind={citation.item.source_kind} age={citation.item.age_text} />
              {citation.item.conflict && <p className="rounded-[14px] bg-unsure-bg px-3 py-2 text-[15px] font-semibold text-unsure">Sources disagree - staff have been alerted.</p>}
              {citation.item.sensor_offline && <p className="rounded-[14px] bg-unsure-bg px-3 py-2 text-[15px] font-semibold text-unsure">The live sensor is silent; this falls back to the last human record.</p>}
              {citation.item.stale && <p className="rounded-[14px] bg-warn-bg px-3 py-2 text-[15px] font-semibold text-warn">This record may be out of date.</p>}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2 text-[13px] font-semibold">
                <span className="badge bg-card2 px-2.5 py-1 text-ink">{citation.item.heading || "General"}</span>
                <span className="badge bg-card2 px-2.5 py-1 text-ink">Dated {citation.item.date}</span>
                <span className="badge bg-card2 px-2.5 py-1 text-ink">Trust: {citation.item.trust}</span>
              </div>
              <p className="whitespace-pre-wrap rounded-[18px] bg-card2 p-4 text-[16px] leading-relaxed">{citation.item.text}</p>
            </div>
          )}
        </div>
      )}
    </dialog>
  );
}

export function CiteChips({ ids, onOpen }: { ids: string[]; onOpen: (id: string) => void }) {
  if (!ids.length) return null;
  return (
    <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((id) => (
        <button
          key={id}
          onClick={() => onOpen(id)}
          className="inline-flex min-h-[26px] min-w-[34px] items-center justify-center rounded-full bg-brand-bg px-2 text-[12px] font-bold text-brand transition-transform active:scale-95"
          aria-label={`Show evidence ${id}`}
        >
          {id}
        </button>
      ))}
    </span>
  );
}
