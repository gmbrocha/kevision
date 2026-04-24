# Backlog

Status: `Backlog / future scope. Not part of the current must-ship path.`

Future-scope items that are real but not v1. Capture here so they don't get lost in `scratch_thoughts.txt` or buried as inline DEFER tags in `rebuild_plan.md`.

Each item: short description, why-it-matters, what we'd need before scoping it.

---

## RFI handling

RFIs (Requests for Information) are a major part of Kevin's day-to-day, separate from but adjacent to the revision-set flow. Two distinct sub-features:

### 1. Auto-cloud the RFI context area

When an RFI references a drawing region but the architect's response *didn't* include a drawn cloud, generate one ourselves around the RFI's referenced area so the change is visually anchored the same way revision-set changes are. The cloud detector / stamp finder primitives we're building for revision sets should be reusable here — we'd be *generating* a synthetic cloud polygon rather than detecting an existing one, but the downstream "what's inside this polygon" extraction is identical.

**Why it matters:** consistency. Kevin's mental model is "thing-in-cloud = thing-to-price/build." If RFIs land without clouds, they break that pattern and force a separate workflow.

**What we'd need before scoping:**
- See real RFI documents from Kevin (Q for him).
- Understand how RFIs anchor to drawings today (sheet ID + coords? text reference? a marker symbol?).
- Confirm the auto-cloud should overlay on the existing sheet PDF vs. produce a derivative artifact.

### 2. Document RFIs that have no drawing changes

Some RFIs are pure Q&A — the architect clarifies something but doesn't actually modify any drawing. These still belong in the audit trail (they're a record that "this question was asked, this answer was given, no work changed"), but they don't fit the cloud-anchored row format.

**Why it matters:** completeness principle. Kevin needs every RFI accounted for, not just the ones that produced drawings.

**What we'd need before scoping:**
- Decide where these rows live: same Excel as the revision-changelog (with a `Type=RFI-NoChange` flag column), separate tab, or separate file?
- Figure out the data we capture: RFI number, question text, answer text, date, originator, addressee, sheets/specs referenced.

---

## (add new backlog items below as they come up)
