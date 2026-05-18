# UI Rectangle Reduction Audit

Date: 2026-05-18

## Main Views Reviewed

- Projects: `/projects`
- Overview and intake/package setup: `/overview`
- Review queue and bulk review: `/changes`
- Review detail, crop adjustment, and geometry correction: `/changes/<change_id>`
- Drawings list and sheet viewer: `/sheets`, `/sheets/<sheet_version_id>`
- Latest Set: `/conformed`
- Export workbook/review packet: `/export`
- Diagnostics: `/diagnostics`
- Settings/audit route: `/settings` as a secondary, non-nav surface

## Most Visually Busy Areas

- Global panels used a full background, border, radius, header divider, and
  nested table wrapper, so every section read as a box inside another box.
- Overview stacked boxed stat blocks, boxed populate status, boxed package run
  history, boxed forms, and boxed tables in one scroll column.
- Review Changes combined segmented filter cages, package filter cages, bulk
  status boxes, and a boxed change-list panel.
- Review detail had dense nested boxes around Pre Review metadata, each Pre
  Review choice, read-only textareas, the image crop, and the action rail.
- Sheet detail boxed every change row in the right rail, competing with the
  actual sheet overlay evidence.
- Latest Set cards had repeated card outlines and hover shadows, which made a
  grid of drawing thumbnails feel heavier than the information required.
- Export generated-file rows were individually boxed inside a boxed panel.

## Common Causes

- Shared `.panel` styling made low-importance layout sections look like
  high-importance containers.
- Segmented filters used an outer border plus inner separators even when the
  state could be shown by the active option alone.
- Stats and progress summaries used table-like boxed cells instead of spacing
  and alignment.
- Repeated item lists used full card borders where row separation was enough.
- Drafting-grid backgrounds and heavy crop shadows added texture behind already
  detailed blueprint imagery.

## Global Reduction Targets

- Make `.panel` a section primitive instead of a card primitive.
- Keep table borders available, but soften them and let flush tables sit inside
  sections without a second cage.
- Convert inactive filter toggles to unboxed text controls with only the active
  state filled.
- Use spacing and row dividers for stats, sheet change lists, and export file
  rows.
- Reduce image-frame shadows and drafting-grid opacity.
- Preserve focus rings, selected states, and keyboard-operated controls.

## Boundaries To Preserve

- Warning, diagnostic, and attention callouts.
- Review status badges, selected Pre Review choice, crop/geometry overlays,
  and accept/reject action boundaries.
- Tables carrying operational audit data such as review queue rows, package
  processing history, export history, diagnostics, and project lists.
- Active/selected navigation and package/review filters.
- Delete confirmation dialog and destructive controls.

## Before/After Intent

Before: the app used the same bordered-box treatment for navigation, sections,
stats, tables, forms, status summaries, rows, cards, and generated-file entries.
That made each screen feel like a stack of competing containers.

After: primary review evidence, active states, warnings, and operational tables
remain clearly bounded. Lower-importance grouping now relies more on spacing,
short headings, softer rules, and aligned rows, so the reviewer can scan the
workflow without every item feeling trapped in a separate rectangle.
