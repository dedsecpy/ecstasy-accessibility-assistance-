"use client";

import { useRef } from "react";
import { Icon, type IconName } from "./Icon";
import type { Mobility } from "@/lib/types";

export const MOBILITY_OPTIONS: { id: Mobility; label: string; detail: string; icon: IconName }[] = [
  { id: "manual_wheelchair", label: "Manual wheelchair", detail: "Self-propelled or pushed", icon: "wheelchair" },
  { id: "powered_wheelchair", label: "Powered wheelchair", detail: "Heavier, needs wider paths", icon: "poweredChair" },
  { id: "mobility_scooter", label: "Mobility scooter", detail: "Needs room to turn", icon: "scooter" },
  { id: "walks_short_distances", label: "Short walks", detail: "With rests, a stick or a frame", icon: "cane" },
  { id: "other", label: "Other", detail: "Tell us in your own words", icon: "more" },
];

export function MobilityPicker({
  value, note, onChange, onNote, name = "mobility", legend = "How you get around",
}: {
  value: Mobility;
  note: string;
  onChange: (m: Mobility) => void;
  onNote: (text: string) => void;
  name?: string;
  legend?: string;
}) {
  const noteRef = useRef<HTMLInputElement>(null);
  const noteId = `${name}-note`;

  const pick = (m: Mobility) => {
    onChange(m);
    if (m === "other") requestAnimationFrame(() => noteRef.current?.focus());
  };

  return (
    <fieldset>
      <legend className="sr-only">{legend}</legend>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {MOBILITY_OPTIONS.map((o) => {
          const on = value === o.id;
          return (
            <label key={o.id} className={`pick-tile ${on ? "is-on" : ""} ${o.id === "other" ? "max-sm:col-span-2" : ""}`}>
              <input
                type="radio"
                name={name}
                value={o.id}
                checked={on}
                onChange={() => pick(o.id)}
                aria-describedby={o.id === "other" && on ? noteId : undefined}
                className="sr-only"
              />
              <span className="pick-icon" aria-hidden="true">
                <Icon name={o.icon} className="h-7 w-7" stroke={1.9} />
              </span>
              <span className="mt-3 block text-[16px] font-semibold leading-tight">{o.label}</span>
              <span className="mt-1 block text-[13px] leading-snug text-muted">{o.detail}</span>
              <span className="pick-radio" aria-hidden="true">
                <Icon name="check" className="h-3.5 w-3.5" stroke={3.2} />
              </span>
            </label>
          );
        })}
      </div>
      {value === "other" && (
        <div className="fade-in mt-3">
          <label htmlFor={noteId} className="mb-1.5 block px-1 text-[15px] font-semibold">Tell us how you get around</label>
          <input
            ref={noteRef}
            id={noteId}
            type="text"
            value={note}
            onChange={(e) => onNote(e.target.value)}
            maxLength={200}
            autoComplete="off"
            placeholder="e.g. I use crutches and can manage a few steps"
            className="field"
          />
        </div>
      )}
    </fieldset>
  );
}
