# Security Policy

Status: project-level security policy summary as of 2026-05-12.

## Current Project Exception

For the current client/project, Kevin and his boss have approved broad GPT/API
use. This permits GPT-assisted labeling and evaluation work for the active
CloudHammer_v2 eval pivot.

This is a project-specific exception, not a blanket policy for future clients
or future projects.

## Future Projects

Future client/project use may require fresh approval before external API use.
Security assumptions should be revisited when:

- the client changes
- the project data changes
- live sensitive documents are introduced under different terms
- deployment shifts from local/dev usage to a broader operating workflow

## Current Private Handoff Posture

The current remote handoff route is `ledger.nezcoupe.net` behind Cloudflare
Access and a local loopback Waitress server. Cloudflare Access is the
authentication gate for this pass; the app is not a public SaaS deployment.

Production mode requires `SCOPELEDGER_WEBAPP_SECRET`, restricts manual
server-path imports to `SCOPELEDGER_ALLOWED_IMPORT_ROOTS`, requires CSRF tokens
for POST requests, and sets secure session cookies plus release security
headers.

At startup, the app loads only allowlisted local environment defaults from
repo-root `.env` and `CloudHammer/.env`; process environment values take
precedence. The allowlist includes OpenAI, handoff serve settings, and live
CloudHammer runtime override keys. Local env files are operator secrets and
must remain uncommitted.

Server-side Pre Review is active only when explicitly configured with
`SCOPELEDGER_PREREVIEW_ENABLED=1` and `OPENAI_API_KEY`. In that mode, detected
region crop images and nearby OCR/context text are sent to the configured
OpenAI model from the server, cached inside the active project workspace, and
shown as provisional suggestions. API output does not approve, reject, hide, or
split review items; the reviewer-selected text/geometry remains final for
export.

Internal review events are stored in each project `workspace.json` and may be
exported as JSONL through the CLI. Treat those files as project-sensitive
operational records: they can include candidate geometry, OCR/context text,
reviewer notes, reviewer identity from Cloudflare Access headers, and
provisional AI metadata. They must not be committed or shared as client-facing
deliverables.

Project deletion is available only from the Projects UI through a destructive
dialog that requires typing `DELETE`. The backend limits deletion to the direct
app-managed workspace for that project id and refuses unmanaged, linked,
reparse-point, nested, or cross-project paths. Deletion is blocked while the
target project has a bulk review job running. Use it for disposable test
cleanup only; archive remains the non-destructive option.

The current audit baseline requires `urllib3>=2.7.0`. Local CUDA `torch`,
`torchaudio`, and `torchvision` wheels may be skipped by `pip-audit` because
they are not PyPI distributions; treat those as separately managed runtime
dependencies.

## Handling Rules

- Record whether labels are GPT-provisional, human-audited, or
  human-corrected.
- Keep auditability for external API-assisted steps.
- Keep API keys server-side only; never commit tunnel credentials, API keys, or
  generated project caches containing client document crops.
- Keep review-event exports internal unless a separate explicit release
  decision says otherwise.
- Do not imply future GPT approval from the current exception.
- Preserve historical security notes in the docs archive.

Historical policy source:

- `docs/archive/docs_archive_2026_05_02/docs_folder/SECURITY_PRIVACY_POLICY.md`
- source/reference copy:
  `docs/references/SECURITY_PRIVACY_POLICY.md`
