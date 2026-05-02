# Security Policy

Status: project-level security policy summary as of 2026-05-02.

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

## Handling Rules

- Record whether labels are GPT-provisional, human-audited, or
  human-corrected.
- Keep auditability for external API-assisted steps.
- Do not imply future GPT approval from the current exception.
- Preserve historical security notes in the docs archive.

Historical policy source:

- `docs/archive/docs_archive_2026_05_02/docs_folder/SECURITY_PRIVACY_POLICY.md`
- source/reference copy:
  `docs/references/SECURITY_PRIVACY_POLICY.md`
