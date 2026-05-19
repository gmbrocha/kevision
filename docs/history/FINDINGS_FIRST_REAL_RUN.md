# First Real Run Findings

Date: 2026-05-10

Status: first real app-run observations only. These notes are not reviewed
labels, not training data, and not client-approved scope decisions.

The throwaway test project used for these observations was reset afterward.
Use this document as a triage input for product polish, review workflow,
OCR/context extraction, and later CloudHammer training/postprocessing work.

## High-Level Read

The first real exploratory run produced many strong cloud hits. The core detection
signal looks promising enough for client-facing review, but the remaining
quality issues fall into a few repeatable buckets:

- partial cloud crops
- overmerged crops containing multiple clouds or too much context
- OCR/context text pulling unrelated nearby material
- symbols and legend references not being interpreted as scoped context
- UI friction in review and notification surfaces
- previous/current comparison correctness needs continued testing

## Product UI Polish

These are client-visible issues that should be handled before or during the
handoff polish pass.

- Flash/status messages should be opaque, normal UI colors, and short-lived.
  The highlighted translucent style is visually distracting.
- Fix awkward upload copy such as `Chunked upload complete: 1 PDF file(s)
  stages as Revision Set 1. Populate...`; it should read as a clean success
  message.
- Keep internal CloudHammer naming out of client-facing UI. Use product terms
  such as `drawing analysis`, `detected regions`, or `revision regions`.
- Confirm Cloudflare Access behavior before sending the client link.
- In the review view, remove secondary `Save` and `Save + Next` controls if
  the intended workflow is only the large accept/reject actions.
- Remove the duplicate highlighted `Scope of Change` block under reviewer
  notes if it repeats the same information and adds visual clutter.

## Already Addressed During Handoff

These items were observed during the run and have since received code-level
fixes, but they should still be watched during the next project populate.

- Drawing index pages must be context only. They should not create cropped
  revision-region review items.
- Uploaded package folders named `Revision Set 1` must parse as Rev 1, not
  Rev 0.
- Previous/current comparison must match by real sheet identity and only use a
  strictly earlier real revision set. A page from the same Rev 1 package should
  not appear as a previous revision.

Test need: verify previous/current comparison on a real multi-revision project
after fresh populate.

## Detection Geometry Findings

The detector is getting many useful hits, including many clean single-cloud
crops. The biggest detection-quality concerns are now geometry quality rather
than total recall.

- Overmerge is a primary issue: multiple nearby clouds or cloud-plus-context
  regions can be grouped into one review item.
- Partial crops remain a primary issue: long clouds or interrupted cloud
  shapes can be detected as only part of the actual revision cloud.
- Splitting needs two tracks:
  - split by intersection or overlap when multiple clouds are merged
  - split/repair long partial detections where the cloud is incomplete
- Preserve good single-cloud examples as positive evidence for future
  training/postprocessing.

## OCR And Scope Text Findings

OCR/context extraction is currently the biggest source of confusing review
text. The cloud hits are often good, but the text attached to them can include
unrelated material.

- OCR is pulling too much from the larger context crop.
- Text extraction should focus on the bounded cloud area and immediately
  adjacent callouts, not broad surrounding drawing areas.
- Random standalone integers and measurement labels should be filtered unless
  they are clearly part of a callout, keynote, tag, or scoped note.
- For legend-like regions, OCR may capture the rest of the legend instead of
  the specific symbol/tag that matters.
- The OCR pipeline needs to favor actual scope references over general page
  clutter.

Observed OCR example:
- Observed OCR text: `Cloud Only - EXHAUST PROVIDE ANTENNA AND CABLING GUARD
  RAIL, PAINT NEW BOOT FOR EXISTING VENT EXTEND LAUNDRY CHUTE THROUGH ATTIC
  FLOOR THROUGH ROOF TO AND PROVIDE MECH VENT HOOD SEE STRUCTURAL DRAWINGS FOR
  INFILL CONSTRUCTION OF EXISTING EXISTING HOUSEKEEPING PAD NOT ALL THE
  KEYNOTES ARE USED ON THIS SHEET PROTECTION`
- Problem: the text includes too much unrelated material and misses likely
  relevant `Z.x`/hexagon tag context inside the cloud.

## Legends, Symbols, And Referenced Scope

Some clouds appear to surround legend or appended legend items. The suspected
workflow is that the clouded legend item defines a symbol/tag, and later clouds
on drawings use that symbol/tag to identify actual scope.

Open question for Kevin:

- Should a cloud around a legend entry become its own review item, or should it
  be treated as context attached to the drawing-cloud items that reference it?

Current working hypothesis:

- The drawing clouds should probably remain the primary review items.
- Legend clouds should provide context to those items when a tag/symbol match
  exists.
- The app should avoid creating duplicate independent review items for both a
  legend definition and every drawing occurrence if they represent the same
  scope relationship.

## Symbol And Callout Extraction Needs

The current set appears to use symbols that carry important scope context.
These need explicit extraction support.

- Hexagons can contain tags such as `Z.8`.
- Circular callouts can contain sheet/detail references or keyed notes.
- These symbols may need lookup against a legend or detail sheet to explain
  the actual scope.
- The app should capture these symbols as structured context, not only as raw
  OCR text.

Candidate future extraction targets:

- hexagon tag detection
- circular callout detection
- detail reference parsing from callouts
- legend/keynote lookup by symbol or tag

## Visual Legibility And Zoom

Large crops and overmerged crops lose legibility when zoomed. This appears to
be a rendering/compression/resolution issue rather than just a UI control
issue.

Needs:

- preserve high-resolution source crops for review zoom
- keep delivery size reasonable
- avoid downsampling the only available review evidence
- support clear zoom on large drawings and large merged regions

Possible direction:

- keep lightweight thumbnails for queue browsing
- load higher-resolution tile/crop assets only in the detail viewer
- regenerate large comparison/crop assets from source PDF at higher DPI when
  the user zooms or opens detail view

## Training And Postprocessing Implications

Do not promote this first-run project directly into training. It was exploratory
and not reviewed as ground truth.

Useful future labels to collect from real review:

- good single cloud
- partial cloud
- overmerged multiple clouds
- false positive
- index/context-only
- OCR too broad
- missed symbol/callout context
- previous/current comparison issue

CloudHammer return point after client handoff:

- Resume at
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.
- Next internal task: resolve or accept rows `20`, `23`, `24`, and `29`.
- After those four crop-precheck rows are settled, continue the existing
  training/postprocessing decision path from that point rather than starting a
  new mining pass from this exploratory app run.

## Immediate Product Follow-Ups

Suggested order:

1. Polish flash/status UI and review controls.
2. Verify Cloudflare Access from a fresh/incognito session.
3. Run a fresh client project populate after the app reset.
4. Test previous/current comparison with a real multi-revision package.
5. Keep recording partial, overmerge, OCR, and symbol/context issues as
   durable review metadata instead of only scratch notes.
