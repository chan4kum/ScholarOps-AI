# Phase 3 tracker — assisted apply

**Done when:** you review a filled packet and click Approve; the audit log records what was sent.

Submit is optional and per-site. Default adapters do **not** POST to live university portals. A signed, expiring, single-use approval token is required before any submit.

| ID | Sub-task | Status |
| --- | --- | --- |
| P3.1 | Tracker + Phase 3 rules (token, no live portal without allowlist) | done |
| P3.2 | Domain: `Application`, `ApplicationEvent`, payload checksum | done |
| P3.3 | Deterministic form fill from profile + packet + opportunity | done |
| P3.4 | Validation (required fields, evidence IDs, UK/GB, packet ready) | done |
| P3.5 | HMAC approval token: expiry, single use, payload binding | done |
| P3.6 | Adapters: `manual` (log-only) and `sandbox` (local fake portal) | done |
| P3.7 | RCTCEOV prompts: leftover fields + claim verification | done |
| P3.8 | API: preview, request-approval, approve, reject, list, events | done |
| P3.9 | UI Apply tab: filled fields, validation, Approve/Reject, audit | done |
| P3.10 | Tests: token, adapters, no submit without approve; run suite | done |

Status values: `pending` · `in_progress` · `done`

## Gate checklist

- [x] Filled form shown for a ready Phase 2 packet
- [x] Validation errors block Approve
- [x] Approve requires a human-issued token (not a hidden auto-submit)
- [x] Token expires and cannot be reused
- [x] Audit log records adapter, checksum, and a redacted sent summary
- [x] Live university portals are not submitted to by default
- [x] Two adapters exist: manual + sandbox
