# Class Rename Map

Old class name → New class name. Apply this find-replace pass to all Jinja templates.
Classes marked **REMOVE** should be deleted (element kept, class dropped or wrapper removed).

## Layout & Shell

| Old | New | Notes |
|-----|-----|-------|
| `.dashboard` | `.page-area` | |
| `.main-content` | `.page-scroll` | |
| `.page-wrapper` | `.page-content` | |
| `.content-header` | `.page-header` | |
| `.page-title` | `.page-title` | *(unchanged)* |
| `.summary-strip` | **REMOVE** | Kill the 4-stat strip on all pages except Overview. On Overview, replace with `.stat-row` |

## Navigation

| Old | New | Notes |
|-----|-----|-------|
| `.sidebar` | `.nav` | |
| `.sidebar-brand` | `.nav-brand` | |
| `.sidebar-link` | `.nav-link` | |
| `.sidebar-link.active` | `.nav-link.active` | |
| `.sidebar-bottom` | `.nav-bottom` | |
| `.project-context` | `.nav-project` | |

## Panels & Cards

| Old | New | Notes |
|-----|-----|-------|
| `.panel` | `.panel` | *(keep, redesigned)* |
| `.panel-header` | `.panel-header` | *(keep)* |
| `.card` | `.panel` | Consolidate — one panel type only |
| `.list-card` | `.panel` | |
| `.metric-card` | **REMOVE** | Replaced by `.stat-row > .stat-block` on Overview only |
| `.stat-card` | **REMOVE** | |
| `.callout` | `.callout` | *(keep, redesigned)* |
| `.attention-banner` | `.callout.callout-check` | |
| `.info-banner` | `.callout.callout-info` | |
| `.flash-message` | `.flash` | |
| `.flash-success` | `.flash.flash-success` | |
| `.flash-warning` | `.flash.flash-warning` | |

## Typography

| Old | New | Notes |
|-----|-----|-------|
| `.eyebrow` | **REMOVE** | Kill all eyebrow labels. Promote content or use `.panel-title` |
| `.section-heading` | `.panel-title` or `<h2 class="page-title">` | Depends on context |
| `.label-sm` | *(inline style or token class)* | Use `font-family: var(--font-mono); font-size: var(--text-xs)` |

## Tables

| Old | New | Notes |
|-----|-----|-------|
| `.data-table` | `.data-table` | *(keep, redesigned)* |
| `.table-wrapper` | `.data-table-wrap` | |
| `.table-row` | `<tr>` | No wrapper class needed |
| `.table-row.next-up` | `.row-next-up` | Applied to first pending `<tr>` only |
| `.table-row.needs-check` | `.row-needs-check` | |

## Status & Badges

| Old | New | Notes |
|-----|-----|-------|
| `.pill` | `.badge` | |
| `.pill-pending` | `.badge.badge-pending` | |
| `.pill-approved` | `.badge.badge-accepted` | Note: "approved" → "accepted" |
| `.pill-rejected` | `.badge.badge-rejected` | |
| `.pill-attention` | `.badge.badge-check` | |
| `.pill-active` | `.badge.badge-active` | |
| `.pill-superseded` | `.badge.badge-superseded` | |
| `.status` | `.badge` | |
| `.status-ok` | **REMOVE** | Don't badge "ok" states |
| `.status-low/medium/high` | **REMOVE** | Not part of new palette |

## Buttons

| Old | New | Notes |
|-----|-----|-------|
| `.button-like` | `.btn` | |
| `.button-like.primary` | `.btn.btn-primary` | |
| `.button-like.secondary` | `.btn.btn-secondary` | |
| `.button-like.ghost` | `.btn.btn-ghost` | |
| `.btn-export` | `.btn.btn-primary` on `/export` only | Remove duplicate CTAs everywhere else |
| `.btn-accept` | `.btn-accept-full` on Change Detail; `.btn.btn-accept` elsewhere | |
| `.btn-reject` | `.btn-reject-full` on Change Detail; `.btn.btn-danger` elsewhere | |

## Filters

| Old | New | Notes |
|-----|-----|-------|
| `.filter-bar` | `.filter-bar` | *(keep)* |
| `.search-input` | `.filter-input` inside `.filter-input-wrap` | |
| `.tab-filter` | `.filter-toggle-group > .filter-toggle` | |

## Review / Change Detail

| Old | New | Notes |
|-----|-----|-------|
| `.review-form` | `.cockpit-form-pane` | |
| `.image-stage` | `.cockpit-image-pane` | |
| `.crop-image` | inside `.cockpit-image-wrap > img` | |
| `.queue-header` | `.cockpit-header` | |
| `.queue-nav` | `.cockpit-nav` | |
| `.keyboard-hints` | `.cockpit-footer` | |
| `.detail-meta` | `.cockpit-meta` | |
| `.scope-field` | `.scope-textarea` | |
| `.notes-field` | `.notes-textarea` | |

## Sheet Detail

| Old | New | Notes |
|-----|-----|-------|
| `.sheet-viewer` | `.sheet-image-area` | |
| `.bbox` | `.bbox` | *(keep — reposition to % coords)* |
| `.version-history` | `.sheet-sidebar > .sheet-version-chain` | |

## Conformed / Latest Set

| Old | New | Notes |
|-----|-----|-------|
| `.conformed-grid` | `.conformed-grid` | *(keep)* |
| `.conformed-card` | `.conformed-card` | *(keep)* |
| `.conformed-card.revised` | `.conformed-card.revised` | *(keep)* |
| `.thumbnail` | `.conformed-thumb` | |
