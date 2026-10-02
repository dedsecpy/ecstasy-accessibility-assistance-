"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "./Icon";
import { api } from "@/lib/api";
import type { VenueSummary } from "@/lib/types";

function haystack(v: VenueSummary): string {
  return [v.name, v.area, v.city, v.kind, v.blurb, ...(v.tags || []), ...v.events.map((e) => e.name)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function placeLine(v: VenueSummary): string {
  return [v.area, v.kind].filter(Boolean).join(" \u00b7 ");
}

export function VenueSearch({ currentId, onSelect }: { currentId: string | null; onSelect: (v: VenueSummary) => void }) {
  const [venues, setVenues] = useState<VenueSummary[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.venues().then(setVenues).catch(() => setVenues([]));
  }, []);

  const results = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    const q = query.trim().toLowerCase();
    return venues
      .filter((v) => terms.every((t) => haystack(v).includes(t)))
      .sort((a, b) => Number(b.name.toLowerCase().startsWith(q)) - Number(a.name.toLowerCase().startsWith(q)) || a.name.localeCompare(b.name))
      .slice(0, 8);
  }, [venues, query]);

  const popular = venues.filter((v) => v.city === "Bengaluru" && v.id !== currentId);

  const choose = (v: VenueSummary) => {
    setQuery("");
    onSelect(v);
  };

  return (
    <div className="min-w-0 space-y-3">
      <div role="search" className="search-field">
        <Icon name="search" className="h-5 w-5 shrink-0 text-muted" stroke={2.2} />
        <label htmlFor="venue-q" className="sr-only">Search venues</label>
        <input
          id="venue-q"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (results[0]) choose(results[0]);
            } else if (e.key === "Escape") {
              setQuery("");
            }
          }}
          placeholder="Search Bengaluru venues, areas or events"
          autoComplete="off"
          enterKeyHint="search"
          aria-controls="venue-results"
        />
        {query && (
          <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="tap flex shrink-0 items-center justify-center rounded-full text-muted">
            <Icon name="close" className="h-4 w-4" stroke={2.4} />
          </button>
        )}
      </div>

      <div id="venue-results" aria-live="polite">
        {query.trim() ? (
          results.length ? (
            <ul className="list fade-in" style={{ ["--inset" as string]: "64px" }} aria-label={`${results.length} venue${results.length === 1 ? "" : "s"} found`}>
              {results.map((v) => {
                const current = v.id === currentId;
                return (
                  <li key={v.id}>
                    <button type="button" onClick={() => choose(v)} aria-current={current || undefined} className="row">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-brand-bg text-brand" aria-hidden="true">
                        <Icon name="building" className="h-5 w-5" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-semibold">{v.name}</span>
                        <span className="block text-[15px] leading-snug text-muted">
                          {placeLine(v)}
                          {v.events.length ? ` \u00b7 ${v.events.length} event${v.events.length === 1 ? "" : "s"}` : ""}
                        </span>
                      </span>
                      {current ? (
                        <Icon name="check" stroke={2.6} className="h-5 w-5 shrink-0 text-brand" />
                      ) : (
                        <Icon name="chevron" className="h-4 w-4 shrink-0 text-muted" stroke={2.2} />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="px-1 text-[15px] text-muted">No venues match &ldquo;{query.trim()}&rdquo;. Try an area like Malleshwaram, or a word like theatre.</p>
          )
        ) : popular.length > 0 ? (
          <div>
            <p className="mb-2 px-1 text-[13px] font-semibold uppercase tracking-wide text-muted">Popular in Bengaluru</p>
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
              {popular.map((v) => (
                <button key={v.id} type="button" onClick={() => choose(v)} className="chip">
                  <Icon name="pin" className="h-4 w-4 text-brand" />
                  {v.name}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
