# Ecstasy demo script (about 4 minutes)

The complaint, live: a wheelchair user checks the evening lecture, the lift fails, their answer flips to NO-GO
and staff are alerted, all without anyone editing a listing.

## Before you start

1. `docker compose -f infra/docker-compose.yml up --build` from the repo root. Wait until
   http://localhost:8000/api/health answers (about 30 s after the images are built).
2. Open two browser windows side by side, both at phone width (or open the visitor one on a phone on the same
   Wi-Fi: `http://<your-PC-IP>:3000`):
   - **Visitor**: http://localhost:3000/plan
   - **Staff**: http://localhost:3000/staff/demo
3. On the Staff window press **Everything working**, so the demo starts from a clean state.

The banner at the top says which AI mode is running ("Bedrock" with AWS keys, otherwise "local fallback").
Both modes produce cited answers; say which one the audience is seeing.

## 1. The honest answer (60 s)

Visitor window, **Plan**:
- Event: **Autumn Lecture Series** (Main Hall, first floor, Thursday 18:30 doors).
- Mobility: **Manual wheelchair**. Needs: **I'd like staff help on arrival**.
- Optional question: "Can I get to my seat for the lecture?" (or use the microphone).
- Press **Check my route**. Point out the streamed steps: desk hours, live sensors, retrieval, safety checks.

Result: **CAUTION**, not "wheelchair accessible":
- The lift is working *now* (live sensor, seconds old) but the visit is a week away, so "check on the day".
- 18:30 is outside desk hours: the intercom is not answered and the Side Gate stays locked, so pre-book.
- The 1:12 ramp has no rest points; ask for help.
- Tap a citation chip (S1, P2...) to open the evidence: who said it, when, and how old it is.
- Scroll to **Where the public listing is wrong**: "Wheelchair accessible" and "Step-free access" are contradicted.

## 2. The lift fails (60 s)

Staff window, **Demo console**: press **Lift stops between floors**.
- Within a few seconds the live board shows **Lift: Out of service** from the lift sensor (the simulated NodeMCU
  publishes fault E21 over MQTT; the worker fuses it).
- Four seconds later the simulated operations team posts a maintenance log entry; the worker extracts a dated fact
  from the free text.
- Open **Alerts**: "Urgent - blocking: Lift out of service". Alerts fire on changes only.

## 3. The visitor's plan changes (45 s)

Visitor window, **Answer**: a **Your plan changed** banner appears without a refresh (server-sent events):
"Lift: was Working, now Out of service". Press **Re-check my route**.

Result: **NO-GO**: "Do not travel on the strength of the listing: the lift is out of service and your destination is
upstairs." The first item to check: "Call 01234 567 890 on the day and ask: 'Is the lift back in service and tested
today?'". This is exactly the visitor in the complaint, warned before travelling instead of at the staircase.

## 4. Not everything is a NO-GO (30 s)

Visitor window, **Plan**: switch the event to **Local History Talk** (ground floor gallery) and check again.
Result: **CAUTION**, not NO-GO: the lift fault is listed as information ("your destination is on the ground floor"),
and the Sunday desk closure becomes the main caution. Same facts, different visit, different answer.

Optional, the second visitor: **Community Fair**, *Walk short distances*, *I need places to sit*,
*I can't manage steep slopes*: CAUTION for 120 m from parking without seating, the ramp, and the foyer chairs.

## 5. When sources disagree or go silent (45 s)

Staff window: press **Everything working** (a recovery log entry is posted), then **Sensor says running,
maintenance log says out of service**.
- The board shows **Sources disagree - verify** and Alerts shows a conflict asking staff to check in person.
- A visitor re-check gives CAUTION with "ask staff to physically confirm the lift is running". Ecstasy never guesses.

Then press **Everything working**, then **Lift sensor goes silent**. About 20 seconds later the lift becomes
**Unknown** (falling back to the last maintenance log, with its age) and a "sensor silent" alert fires. Silence is
never treated as "working".

## 6. Close (20 s)

- Staff, **Listing health**: each public claim graded against live evidence, events at risk, and a drafted honest
  listing.
- Staff, **Daily check**: one tap per feature; human checks expire after 24 hours so they cannot go stale silently.
- Answer page, **How this answer was made**: the retrieval queries, passages with scores, validators and timing.

Reset at any time with **Everything working** in the Demo console.

## Scripted version

`python eval/smoke_api.py http://localhost:8000` runs steps 1 to 4 against the API and prints PASS or FAIL (needs
`httpx`; or run it inside the stack: `docker compose -f infra/docker-compose.yml run --rm --no-deps api python
/app/eval/smoke_api.py http://api:8000`).
