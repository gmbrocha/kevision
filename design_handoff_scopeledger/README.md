# ScopeLedger — Design Handoff

## Overview
Complete front-end redesign of ScopeLedger, a local desktop web app that ingests construction blueprint revision sets (PDFs), detects clouded change areas, and routes them through a human review queue before exporting an Excel workbook for contractor pricing. The user is Kevin — a construction reviewer, not a developer.

## About the Design Files
The files in this bundle are **high-fidelity HTML/CSS design references** — interactive prototypes demonstrating intended look, layout, and behavior. They are not production code to copy directly. The task is to **recreate these designs in the existing Flask + Jinja2 project** using its template structure, `app.css`, and static assets. The HTML prototypes use React + Babel for interactivity in the mockup only; the real implementation should use Jinja2 templates with plain HTML/CSS and minimal vanilla JS.

## Fidelity
**High-fidelity.** Colors, typography, spacing, component shapes, and interactions are final. Recreate pixel-accurately using the token values in `tokens.css`. The only placeholder elements are `placehold.co` thumbnail images — replace with real PDF-extracted crops and sheet thumbnails.

---

## Files in this Package

| File | Purpose |
|------|---------|
| `tokens.css` | CSS custom properties — full design token set, dark + light themes |
| `app.css` | All component styles, keyed to token variables |
| `rename_map.md` | Old class name → new class name mapping for template migration |
| `component_inventory.html` | Every component rendered in isolation with usage notes |
| `prototype/index.html` | Interactive prototype — navigate all 8 screens |

---

## Design Tokens (`tokens.css`)

Apply to the root template's `<html>` element. Dark mode is default (`data-theme` not set or `data-theme="dark"`). Light mode: set `data-theme="light"` on `<html>`.

### Key Token Reference

```css
/* Surfaces (4 levels deep) */
--surface-canvas      /* page background */
--surface-base        /* nav, panel backgrounds */
--surface-raised      /* cards, table rows on hover */
--surface-overlay     /* dropdowns, modals */
--surface-input       /* form inputs, textareas */

/* Accent — amber, used sparingly */
--accent              /* primary interactive color */
--accent-dim          /* 32% opacity accent, for selections */
--accent-quiet        /* 12% opacity accent, for row highlights */

/* Status */
--status-pending      --status-pending-bg
--status-accepted     --status-accepted-bg
--status-rejected     --status-rejected-bg
--status-check        --status-check-bg    /* "needs check" amber warning */

/* Text — 4 levels */
--text-primary        /* headings, table values */
--text-secondary      /* labels, subtitles */
--text-tertiary       /* metadata, column headers */
--text-disabled

/* Rules */
--rule-hairline        /* table borders, panel dividers */
--rule-soft            /* between-row rules */
--rule-focus           /* focus rings (= accent) */

/* Typography */
--font-sans            /* IBM Plex Sans — all UI text */
--font-mono            /* IBM Plex Mono — sheet IDs, codes, numbers */

/* Spacing scale */
--sp-1 (4px) through --sp-16 (64px)

/* Radii */
--radius-sm (2px)  --radius-md (3px)  --radius-lg (5px)  --radius-xl (8px)
```

---

## Screens / Views

### 1. Project Overview `/`

**Purpose:** Landing page. One-glance answer to: what package am I in, how many decisions do I owe, where do I click to start?

**Layout:**
- Full-height two-column: fixed left nav (220px) + scrollable main area
- Hero section: project title (28px semibold, `--font-sans`, `letter-spacing: -0.025em`) + subtitle + package chip. Right side: single large CTA button.
- Stat row: 5-column flex strip, `border: 1px solid --rule-hairline`, no outer card container. Numbers in `--font-mono` at 34px. Fifth column holds progress bar (4px track, `--accent` fill).
- Conditional callout if `needs_check > 0` — amber border, amber icon.
- Revision packages table in a `panel` container.
- Export readiness panel at bottom.

**Do not add:** metric cards, workflow step strips, PDF warnings table, "recent items" sections.

**CTA logic:**
- If `pending > 0` → "Review next — N pending" (primary, links to first pending change detail)
- If `pending === 0` → "Export workbook" (primary, links to `/export`)

---

### 2. Review Changes `/changes`

**Purpose:** The queue Kevin lives on. Filterable list of all change items for the active package.

**Layout:**
- Page header: title + pending count subtitle + "Start reviewing" CTA (primary button, jumps to first pending change detail)
- Filter bar: search input + status toggle group (All / Pending / Accepted / Rejected / Needs check with counts)
- Conditional callout for `needs_check > 0`
- Full-width data table

**Table columns:** checkbox · Sheet (mono) · Cloud (mono, accent color) · Scope of change (truncated, max-width) · Discipline · Status badges · "Review →" ghost button

**Row states:**
- First pending row: `background: --accent-quiet`, `border-left: 2px solid --accent` — the "next up" row
- Needs-check rows: `border-left: 2px solid --status-check`
- "Next up" rows get a pulsing 6px amber dot + "Next" label before the sheet ID

**Bulk actions:** When checkboxes selected, show "N selected · Accept all · Reject all" in the header actions area.

---

### 3. Change Detail `/changes/<id>` ← Most important screen

**Purpose:** Cockpit for reviewing one change at a time. Keyboard-driven. Image dominates.

**Layout — full height, no scroll:**
```
┌─────── 48px cockpit header ────────────────────────────────────────┐
│ ← Back   Sheet · Cloud · Rev   [status badge]   ‹ N/total ›  btn  │
├──────────────────────── 58% ──────────┬────── 42% ────────────────┤
│                                       │  metadata grid (2-col)    │
│  [CROP IMAGE — centered, max 58vh]    │  ─────────────────────    │
│                                       │  scope textarea           │
│  drafting grid texture behind image   │  notes textarea           │
│                                       │  [save notes btn]         │
├── context strip (sheet title, disc) ──┤  ─────────────────────    │
│   [Full sheet →]                      │  [✓ Accept + Next  A]     │
│                                       │  [✗ Reject + Next  R]     │
├──────── 36px keyboard hint footer ────┴───────────────────────────┤
│  [A] accept+next  [R] reject+next  [S] save  [ ] [ ] navigate     │
└────────────────────────────────────────────────────────────────────┘
```

**Keyboard shortcuts (implement with `keydown` listener, skip if `<textarea>` focused):**
- `A` → accept + advance to next change
- `R` → reject + advance to next change
- `S` → save notes without advancing
- `[` → previous change
- `]` → next change

**Accept button:** `height: 44px`, `background: --status-accepted`, `color: dark inverse`, full-width
**Reject button:** `height: 44px`, `background: --status-rejected-bg`, `color: --status-rejected`, `border: 1px solid rejected/0.4`, full-width — on hover becomes solid red

**Image pane background:** faint drafting grid using `background-image` with two linear-gradients at `--rule-soft` color, `32px` grid, `opacity: 0.4`. Position: `::before` pseudo-element.

**Kbd glyphs in footer:** `background: --surface-raised`, `border: 1px solid --rule-hairline`, `border-bottom-width: 2px`, `border-radius: --radius-sm`, mono font, 10px.

---

### 4. Drawings `/sheets`

**Purpose:** Flat list of all sheet versions (active + optionally superseded), filterable.

**Layout:** Page header + filter bar (search + discipline toggle group) + "Show/hide superseded" button + data table.

**Table columns:** Sheet (mono) · Title · Revision (accent color) · Previous rev (tertiary mono) · Discipline · Changes (accent if > 0, else "—") · Status badge · Warning count (amber if > 0) · "View →"

**Superseded rows:** `opacity: 0.55`

---

### 5. Sheet Detail `/sheets/<id>`

**Purpose:** Full sheet image with detected cloud bounding boxes overlaid (clickable into change detail). Version chain sidebar.

**Layout — full height, no page scroll:**
- Header: back button + sheet ID (mono, 16px semibold) + status badge + sheet title + "Review N changes" CTA
- Content: CSS grid `1fr 280px`
  - Left: sheet image area with drafting-grid background (`40px` grid, `opacity: 0.35`). Image centered. Bounding boxes positioned absolutely as `%` of image dimensions.
  - Right: sidebar with version chain (timeline dots + lines) + change items list for current revision

**Bounding boxes (`.bbox`):**
- `border: 1.5px solid --accent`
- `background: --accent-quiet`
- Hover: `background: --accent-dim`
- Label chip above each box: `background: --accent`, `color: inverse`, mono 11px

**Version chain:**
- Current revision: filled amber dot
- Previous revisions: hollow dots with vertical hairline connecting them
- Each entry shows revision label + change count

---

### 6. Latest Set `/conformed`

**Purpose:** Drawing index — for each sheet number, shows the latest detected version and what it supersedes. Used to verify the tool picked correct revisions.

**Layout:** Page header + info callout + CSS grid `repeat(auto-fill, minmax(180px, 1fr))`, `gap: 16px`

**Card structure:**
- Thumbnail area: `aspect-ratio: 17/11`, drafting grid background texture, placeholder/real image at 50% opacity
- "Revised" badge (amber, top-right): shown only if sheet was revised in the current package
- Info area: sheet ID (mono, 12px semibold) · title (12px, truncated) · version chain (`Rev 04 ← Rev 03` in mono 10px, current rev in accent color)
- Revised cards: `border-color: oklch(0.71 0.130 68 / 0.4)`

**This should look like a drawing index sheet, not a Pinterest grid.** Keep cards small and dense. Sheet ID is the visual anchor, not the thumbnail.

---

### 7. Export Workbook `/export`

**Purpose:** Generate / re-generate the Excel workbook and review packet. One canonical surface for this action.

**Layout:** Max-width 720px, stacked panels:
1. Review status panel: stat numbers + progress bar + pending-items callout
2. Generate panel: file list (3 output files) + large generate button
3. Export history table

**Generate button:** Full-width, `height: 48px`, primary style. Shows "Generating…" with spinning refresh icon during generation. Shows "Re-generate" after first run.

**File list:** Each file shown as a row with icon + filename (mono) + description (secondary). Files are dimmed (opacity 0.5) until first generation.

**Only one "generate workbook" button exists in the entire app** — on this page. The nav link and any other references are navigation, not duplicate CTAs.

---

### 8. Diagnostics `/diagnostics`

**Purpose:** Quiet utility page for PDF health. Not part of the review workflow — engineer/admin use.

**Layout:** Standard page header (subtitle: "not part of the review workflow") + optional issue callout + ingested PDFs table + ingestion summary panel.

**Table columns:** File (mono) · Pages · Size · Clouds (accent) · Text layer (Vector / Rasterized+OCR warning) · Issues

**Tone:** Understated. No bright colors unless there's an actual issue. "All files healthy" badge in header when clean.

---

## Component Reference

### Nav Sidebar
- Width: `220px` fixed
- Brand mark: 24×24px amber square, `--radius-sm`, file icon SVG
- Project context section: shows active project name + current package + date
- Nav links: `48px` hit height, `15px` line icon, left `2px` amber border on active state, `--accent-quiet` background on active
- Pending badge on "Review Changes": mini pill, `background: --accent`, `color: inverse`, mono 10px
- Diagnostics at bottom, separated by hairline

### Status Badges
Three status values only: **Pending** (blue-gray) · **Accepted** (green) · **Rejected** (red). Plus **Needs check** (amber) as an additive flag alongside status. Plus **Active** (green) / **Superseded** (gray) for sheets.

Structure: `<span class="badge badge-{status}"><span class="badge-dot"></span>Label</span>`

### Buttons
| Class | Use |
|-------|-----|
| `.btn.btn-primary` | One per screen. The most important action. |
| `.btn.btn-secondary` | Secondary actions with borders |
| `.btn.btn-ghost` | Tertiary, table row actions, back links |
| `.btn-accept-full` | Change Detail accept — full-width, solid green |
| `.btn-reject-full` | Change Detail reject — full-width, ghost red → solid on hover |

Sizes: default `height: 32px` · `.btn-lg` 40px · `.btn-xl` 48px · `.btn-sm` 26px

### Data Table
Wrap in `.data-table-wrap` (border + radius). `<table class="data-table">`. Column headers: mono 10px, tertiary, uppercase, 0.07em tracking. Row height: compact mode ~38px. Hover: `--surface-hover`.

### Callout / Banner
`.callout.callout-check` (amber) or `.callout.callout-info` (blue-gray). Icon + text. Used sparingly — one per page maximum.

---

## Typography Rules

| Use | Font | Size | Weight | Notes |
|-----|------|------|--------|-------|
| Page titles | IBM Plex Sans | 20px | 600 | `letter-spacing: -0.02em` |
| Section/panel titles | IBM Plex Sans | 12px | 500 | |
| Body / table cells | IBM Plex Sans | 12–13px | 400 | |
| Sheet IDs, codes, numbers | IBM Plex Mono | 11–13px | 400–500 | `letter-spacing: 0.02–0.06em` |
| Column headers | IBM Plex Mono | 10px | 500 | uppercase, `letter-spacing: 0.07em` |
| Kbd glyphs | IBM Plex Mono | 10px | 500 | |
| Stat values | IBM Plex Mono | 34px | 600 | `letter-spacing: -0.02em` |

Load via Google Fonts: `family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600`

---

## Patterns to Avoid (the "No" list)

These were intentionally excluded — do not re-introduce them:

- **No summary strip on every page.** The 4-number stat strip (To Review / Accepted / Needs Check / PDF Warnings) should only appear on the Overview. Never on Change Detail, Drawings, Export, etc.
- **No eyebrow labels** ("Current Package", "Review Summary", "Drawing Packages"). Use section titles or nothing.
- **No teal/seafoam accent.** The accent is amber (`oklch(0.71 0.13 68)`). Teal was the old palette — do not reuse it.
- **No gradient top borders on cards.** Every panel has the same `border: 1px solid --rule-hairline`. No colored top accents.
- **No "Open Workbook" button outside `/export`.** Export is a single canonical surface.
- **No status pills beyond the defined set.** Don't add "attention", "active review", "warning", "high/medium/low" variants. The palette is: pending / accepted / rejected / needs-check / active / superseded.
- **No rounded cards with colored left-border accents** as a decoration pattern (the left border on "next up" queue rows is functional state, not decoration).
- **No charts, sparklines, or trend indicators.** Kevin doesn't need them.
- **No "Welcome back, Kevin"** or time-of-day greetings anywhere.
- **No glassmorphism, blur overlays, or gradient hero sections.**

---

## Assets Required

| Asset | Source | Notes |
|-------|--------|-------|
| IBM Plex Sans | Google Fonts | Weights 300, 400, 500, 600 |
| IBM Plex Mono | Google Fonts | Weights 400, 500 |
| Line icons | Lucide icon set (v0.441) | Stroke width 1.75, single weight throughout. Icon paths in `components.jsx` |
| Sheet thumbnails | PDF extraction pipeline | Replace `placehold.co` URLs |
| Cloud crop images | PDF extraction pipeline | Replace `placehold.co` URLs |

---

## Flask / Jinja2 Implementation Notes

- Apply `data-theme="dark"` to `<html>` by default. Persist theme choice in a cookie or `localStorage`.
- The `app.css` file replaces the existing `app.css`. Load `tokens.css` before `app.css`.
- For the Change Detail keyboard shortcuts, add a `<script>` block to the template that fires `keydown` listeners on the page, posting to the accept/reject Flask route via `fetch()` and then redirecting to the next pending change.
- The "next up" row in the queue needs the first pending change ID passed from the Flask route context. Apply the `.row-next-up` class to that `<tr>`.
- The bounding box positions (`.bbox` elements) are expressed as percentages of the source image — store them as `left_pct`, `top_pct`, `width_pct`, `height_pct` in the database and render inline styles in the Jinja template.
- The progress bar fill width is `(accepted + rejected) / total * 100` — compute in the route and pass as a template variable.
