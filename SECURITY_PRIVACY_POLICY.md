# Security And Privacy Policy

Status: draft policy for ESA review before live sensitive project use.

This policy defines how KEVISION handles project data and when, if ever,
external AI APIs may be used. It is intentionally conservative because live
revision packages, RFIs, drawing sheets, title blocks, stamps, room names, and
project metadata can contain sensitive owner, facility, contractor, or bid
information.

## Policy Summary

KEVISION is local-first by default.

- Source PDFs stay local.
- Text layers stay local.
- Metadata stays local.
- Workbooks and review logs stay local.
- RFI, modification, Government-letter, and shared-file documents stay local.
- Full drawing pages stay local.

External API use is not part of the core product path. It may be considered
only as an ESA-approved fallback for low-confidence cloud-shape confirmation
after local sanitization.

## Approval Gate

Live ESA project data must not be sent to any external API until ESA has
reviewed and accepted this policy or a successor policy.

Until approval:

- External API calls may use only synthetic, public, or explicitly approved
  non-sensitive test material.
- Local CloudHammer inference, local review, and local exports may continue.
- Any OpenAI API use for development must be treated as non-production
  research data unless ESA explicitly approves otherwise.

## Allowed External API Purpose

The only currently contemplated external API purpose is:

- confirm whether a sanitized low-confidence image patch visually resembles a
  revision-cloud shape.

The external API must not be used for live ESA data to:

- read OCR text
- extract scope
- interpret RFI responses
- identify project, owner, facility, room, or sheet metadata
- generate workbook rows
- classify subcontractor responsibility
- price work
- summarize confidential project documents

## Allowed External API Input

If ESA approves external fallback use, the API input must be a sanitized visual
derivative of a candidate cloud region.

Allowed inputs:

- candidate-region crop only, not a full page
- raster image with embedded metadata removed
- text-layer-free image produced by local rasterization
- masked or cropped image with title blocks and unrelated drawing context
  removed where practical
- preferably binarized, edge-only, contour-only, or otherwise reduced visual
  form that preserves cloud scallop geometry while suppressing readable project
  content

Disallowed inputs:

- source PDFs
- full sheets or full drawing pages
- unredacted crops
- title blocks
- stamps and signatures
- filenames and raw source paths
- sheet names and sheet numbers
- project, owner, facility, contractor, or Government names
- RFI numbers or modification identifiers
- room names, equipment schedules, notes, and other readable text
- text-layer extracts
- workbook rows or review notes

## Sanitization Requirements

Before any approved API fallback call, KEVISION must create a sanitized image
artifact locally.

Minimum sanitization requirements:

- crop to the low-confidence candidate region with only necessary local margin
- rasterize locally so no PDF text layer is transmitted
- write a new image without embedded metadata
- strip or avoid source filename/path in the outbound payload
- mask known title-block or page-border regions if they intersect the crop
- avoid sending readable text when a shape-only representation will work

Preferred sanitization modes:

- `binary_mask`: high-contrast black/white shape mask
- `edge_only`: edge/contour image that preserves scallop geometry
- `cloud_band`: cropped perimeter band around the suspected cloud outline

Raw candidate crops are not approved external API payloads.

## Configuration Gate

External API fallback must be disabled by default.

Required defaults:

```text
external_api_enabled = false
allow_live_project_api = false
```

Live project API use requires all of the following:

- ESA approval recorded in project configuration or deployment notes
- explicit operator opt-in
- configured sanitization mode
- audit logging enabled
- dry-run/report reviewed before first live use

## Dry Run / Report Mode

Before any live external API call, the system must support a dry-run/report
mode that shows what would be sent.

The report should include:

- local candidate ID
- source page hash or local page ID hash
- sanitization mode
- sanitized image dimensions
- outbound byte size
- reason for fallback
- model/provider that would be called
- local path to the sanitized artifact for human inspection

The report must not include raw source paths, owner/project names, full sheet
images, or raw text content.

## API Audit Log

Every external API fallback call must write a local audit record.

Required fields:

- timestamp
- local candidate ID
- source revision set/page ID hash, not raw filename
- sanitization mode
- model/provider
- reason for fallback
- outbound artifact hash
- response summary
- whether the response changed local confidence or routing
- later human review result when available

Audit logs are local project records and must not be used as training truth by
themselves.

## OpenAI Vendor Review Notes

OpenAI's public API data-control documentation currently states that API data
is not used to train or improve OpenAI models unless the customer opts in.
OpenAI also describes abuse-monitoring logs that may contain prompts,
responses, and derived metadata, retained by default for up to 30 days unless
another approved retention control applies.

References for ESA/vendor review:

- OpenAI API data controls:
  https://platform.openai.com/docs/models/how-we-use-your-data
- OpenAI business data privacy:
  https://openai.com/business-data/
- OpenAI enterprise privacy:
  https://openai.com/enterprise-privacy/

ESA should decide whether the project requires:

- Zero Data Retention
- Modified Abuse Monitoring
- specific contract terms or a Data Processing Addendum
- provider audit logs
- project-level API keys and access controls
- a prohibition on all external API use for live projects

This repo must not assume those controls are in place until ESA confirms them.

## RFI And Modification Documents

RFI, Government-letter, shared-file, and modification-tracker documents are
higher sensitivity than cloud-shape snippets.

Policy:

- no external API use for live RFI/modification documents unless separately
  approved by ESA
- no external OCR or summarization for live RFI/modification documents under
  the cloud-confirmation fallback approval
- future RFI automation needs its own data-flow review

## Human Review And Training Truth

External API responses are advisory only.

- API output may raise or lower a local candidate's review priority.
- API output may not become training truth without human review.
- API output may not silently approve live deliverable rows.
- Human-reviewed labels and review decisions remain the source of truth.

## Incident Rule

If unapproved sensitive data is sent externally:

1. Stop all external API usage immediately.
2. Preserve local audit logs and outbound artifacts.
3. Identify affected source documents and candidate IDs.
4. Notify the project owner and ESA contact.
5. Do not resume external API usage until the incident is reviewed and the
   policy/configuration is corrected.

## Current Project Status

As of this draft:

- CloudHammer is the primary local detector.
- The real backend scanner/exporter can consume a CloudHammer release manifest.
- OpenAI API usage exists only in CloudHammer prelabeling/research utilities.
- No live ESA project API policy has been approved.

The next implementation step, after ESA review, is to build the sanitizer,
dry-run report, configuration gate, and audit log before any live-data fallback
is enabled.
