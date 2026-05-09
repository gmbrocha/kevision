# Deployment

Status: deployment notes as of 2026-05-09.

ScopeLedger is in a private client-handoff deployment posture, not a public
SaaS posture. The current release path is a Windows-hosted app behind the
existing Cloudflare Tunnel and Cloudflare Access application at
`ledger.nezcoupe.net`.

## Current Assumptions

- Cloudflare Access is the authentication gate.
- The app binds to `127.0.0.1:5000` in `--production`; do not bind it to a
  public interface.
- Production mode requires `SCOPELEDGER_WEBAPP_SECRET`.
- Manual server-path imports are restricted to
  `SCOPELEDGER_ALLOWED_IMPORT_ROOTS`.
- Browser PDF intake is chunked through the app to avoid Cloudflare request
  body limits.
- Populate runs synchronously and may take minutes.
- Generated datasets, model runs, and large outputs stay local unless
  explicitly promoted.
- `CloudHammer_v2` remains the active eval-pivot workspace; client handoff work
  does not change frozen eval/training policy.

## Current Handoff Controls

- Waitress serves the Flask app locally.
- Cloudflare Tunnel publishes `ledger.nezcoupe.net`.
- Cloudflare Access allowed-user policy must be confirmed before sharing.
- Production POSTs require CSRF tokens.
- Session cookies are secure, HTTP-only, and `SameSite=Lax`.
- Release headers include `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, and `Cache-Control: no-store`.
- Chunked upload temporary files are removed on success, browser abort, or
  stale cleanup.
- Unreadable PDFs are kept as diagnostics instead of crashing Populate.

## Before Broader Rollout

- Move Populate to a background worker with status polling.
- Add durable process supervision for the app and tunnel.
- Define artifact retention and workspace cleanup policy.
- Add app-level identity/JWT validation if relying on more than Cloudflare
  Access as the outer gate.
- Revisit security approval for any new client/project.
