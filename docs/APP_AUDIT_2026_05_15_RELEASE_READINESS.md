# Release Readiness App Audit - 2026-05-15

Scope: final application-layer audit before private client handoff. This pass
covered the current web app review/export surface, high-risk geometry evidence
paths, package/revision carry-forward assumptions, and current docs. It did not
change CloudHammer_v2 training/eval artifacts, source revision packages, model
weights, frozen eval pages, or generated app workspaces.

## Paths Audited

- Review/detail geometry selection, full-sheet drawing overlays, and explicit
  crop/partial/overmerge correction precedence.
- Previous/current comparison image generation used by workbook and review
  packet exports.
- Review packet selected crop, previous/current comparison, and marked source
  context assets.
- Revision changelog workbook layout for metadata rows and revision/date text.
- Export page handoff links and generated artifact controls.
- Current state, roadmap, product delivery, and next-action docs.

## Findings Fixed

### High-resolution sheet overlays used the wrong coordinate scale

Finding: sheet-detail drawing overlays were scaled against the browser image's
high-resolution natural pixel size while stored review boxes were in base sheet
coordinates. This made boxes appear too small and displaced up/left on active
and superseded drawing views.

Fix: sheet views now expose stored sheet coordinate dimensions to the browser,
and the overlay scaler uses those dimensions. Selected Pre Review 2 geometry is
also sanity-checked before it can replace the original candidate box on
full-sheet overlays; explicit reviewer corrections still take precedence.

### Review packet source context could crop/mark at the wrong scale

Finding: the review packet source-context asset assumed `cloud.page_image_path`
or `sheet.render_path` had the same pixel dimensions as stored sheet
coordinates. A high-resolution page image could therefore draw the marked
source context in the wrong place.

Fix: review packet source-context boxes are now scaled from stored sheet
coordinates into the actual page-image pixel dimensions before crop and
highlight rendering.

### Export workbook metadata row was too short for revision date text

Finding: the revision/date metadata row could require manual row-height changes
in Excel to display the full `Revision #` plus date text.

Fix: each export block's metadata row now has a taller fixed height, and dated
revision labels render the date on a second line.

### Export page exposed an unnecessary Google Drive folder link

Finding: the export view still included a hard-coded Drive-folder shortcut that
was not part of the current private handoff flow.

Fix: the shortcut and template context were removed from the current app export
view. The stale wording remains only in archived/reference docs.

## Findings Confirmed Without New Code

- Previous/current comparison rendering already scales current and prior sheet
  coordinates through sheet dimensions before drawing crops. A regression test
  now covers the high-resolution image fallback path.
- Review queue visibility remains revision-scoped: newer packages do not
  automatically hide older active review items on the same sheet number.
- Confirmed legend items are soft-hidden from normal queues, overlays, review
  packets, pricing candidates, and workbook export while staying in
  `workspace.json` provenance.
- The private handoff path remains app-layer work. CloudHammer_v2 training/eval
  returns after the demo at the existing crop-precheck blocker.

## Morning Smoke Checklist

1. Start from `/projects`, create a fresh handoff/smoke project, upload or
   import the reduced package PDFs, and run Populate.
2. Confirm Overview package history shows reused/processed states and Pre
   Review progress does not stick in a stale running state.
3. Open Drawings/Latest Set for PL505-style sheets and confirm green review
   overlays align with clouds.
4. In Review Changes, select Pre Review 1/2 on one item, use `Mark as legend`
   on one legend-like item if present, and approve at least one normal item.
5. Export workbook and review packet, then confirm revision/date metadata rows
   display without manual height changes and source-context highlights align.
6. After client handoff testing, return to the CloudHammer_v2 crop-precheck
   return point documented in `docs/CURRENT_STATE.md`.

## Residual Risk

- Browser-cached `webapp/static/app.js` may require a hard refresh in an open
  tab before the overlay scaling change is visible.
- Full-sheet correction for partials where the missing geometry sits outside
  the current crop remains a follow-up.
- The private handoff still runs long Populate work inside the local app
  process. Durable background process supervision is deferred unless the demo
  becomes a longer-lived deployment.
