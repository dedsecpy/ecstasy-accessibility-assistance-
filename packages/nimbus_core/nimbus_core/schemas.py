"""Pydantic models shared by the API, the RAG pipeline and the eval runner."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .features import FEATURES, MOBILITY_LABELS, MOBILITY_QUERY_TERMS, STATUS_LABELS

Mobility = Literal["manual_wheelchair", "powered_wheelchair", "mobility_scooter", "walks_short_distances", "other"]
Verdict = Literal["go", "caution", "no_go"]
WalkRange = Literal["short", "medium", "long"]
StepsAbility = Literal["none", "few", "flight"]
Arrival = Literal["blue_badge", "car", "taxi", "public_transport", "on_foot"]

WALK_TEXT = {"short": "under 50 m", "medium": "50 to 200 m", "long": "over 200 m"}
STEPS_TEXT = {"none": "cannot manage any steps", "few": "can manage one or two steps", "flight": "can manage a flight of stairs with a rail"}
ARRIVAL_TEXT = {
    "blue_badge": "arrives by car with a blue badge",
    "car": "arrives by car",
    "taxi": "arrives by taxi drop-off",
    "public_transport": "arrives by public transport",
    "on_foot": "arrives on foot or wheeling",
}


class Profile(BaseModel):
    mobility: Mobility = "manual_wheelchair"
    mobility_note: str = Field("", max_length=200)
    needs_seating: bool = False
    avoid_slopes: bool = False
    needs_assistance: bool = False
    free_text: str = ""
    # Travel-profile questionnaire; every field is optional so older clients keep working.
    walk_range: WalkRange | None = None
    steps: StepsAbility | None = None
    chair_width_mm: int | None = Field(default=None, ge=400, le=1500)
    hearing_support: bool = False
    visual_support: bool = False
    quiet_space: bool = False
    needs_toilet: bool = False
    arrival: Arrival | None = None
    companion: bool = False

    def describe(self) -> str:
        note = self.mobility_note.strip()
        parts = [f"gets around: {note}" if self.mobility == "other" and note else MOBILITY_LABELS.get(self.mobility, self.mobility)]
        if self.chair_width_mm:
            parts.append(f"chair or scooter is {self.chair_width_mm} mm wide")
        if self.walk_range:
            parts.append(f"can walk or wheel {WALK_TEXT[self.walk_range]} without a rest")
        if self.steps:
            parts.append(STEPS_TEXT[self.steps])
        if self.needs_seating:
            parts.append("needs seating and rest points along the route and at the destination")
        if self.avoid_slopes:
            parts.append("cannot manage steep slopes")
        if self.needs_assistance:
            parts.append("would like staff assistance on arrival")
        if self.hearing_support:
            parts.append("uses a hearing aid and needs a working hearing loop")
        if self.visual_support:
            parts.append("has low vision and benefits from clear signage and guidance")
        if self.quiet_space:
            parts.append("prefers quiet, low-crowd spaces")
        if self.needs_toilet:
            parts.append("needs an accessible toilet")
        if self.arrival:
            parts.append(ARRIVAL_TEXT[self.arrival])
        if self.companion:
            parts.append("travels with a companion or carer")
        if self.free_text.strip():
            parts.append(f"in their own words: {self.free_text.strip()}")
        return "; ".join(parts)

    def query_terms(self) -> str:
        t = [MOBILITY_QUERY_TERMS.get(self.mobility, "")]
        if self.needs_seating or self.walk_range == "short":
            t.append("seating bench chair rest")
        if self.avoid_slopes:
            t.append("ramp slope gradient steep")
        if self.needs_assistance:
            t.append("assistance desk hours pre-book intercom")
        if self.hearing_support:
            t.append("hearing loop induction loop")
        if self.needs_toilet:
            t.append("accessible toilet")
        if self.arrival in ("blue_badge", "car", "taxi"):
            t.append("parking blue badge drop-off")
        if self.chair_width_mm:
            t.append("width narrow path")
        if self.mobility == "other" and self.mobility_note.strip():
            t.append(self.mobility_note.strip())
        return " ".join(t)

    @property
    def short_range(self) -> bool:
        return self.mobility == "walks_short_distances" or self.walk_range == "short"

    @property
    def wide_chair(self) -> bool:
        return self.mobility in ("powered_wheelchair", "mobility_scooter") or (self.chair_width_mm or 0) >= 700


class AskRequest(BaseModel):
    question: str = ""
    profile: Profile = Field(default_factory=Profile)
    event_id: str | None = None
    visit_at: str | None = None  # local ISO datetime at the venue, optional
    now: str | None = None  # override "now" (eval and demos); local ISO


class Cited(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)


class AnswerBody(BaseModel):
    verdict: Verdict
    headline: str
    summary: str
    route: list[Cited] = Field(default_factory=list)
    warnings: list[Cited] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)
    discrepancies: list[Cited] = Field(default_factory=list)


ReportKind = Literal["visitor_report", "staff_note", "maintenance_log"]


class ReportIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    reporter: Literal["visitor", "staff"] = "visitor"
    kind: ReportKind | None = None
    needs: str = ""


class StaffCheckItem(BaseModel):
    feature: str
    status: str
    note: str = ""

    def valid(self) -> bool:
        return self.feature in FEATURES and self.status in STATUS_LABELS and self.status != "verify"


class StaffCheckIn(BaseModel):
    staff_name: str = ""
    items: list[StaffCheckItem]


class ScenarioIn(BaseModel):
    venue_id: str = "riverside_hall"
    scenario: str
