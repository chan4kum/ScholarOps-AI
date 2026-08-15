# Phase 2 tracker — document packet

**Done when:** for one HIGH PRIORITY PhD, the system produces a proposal draft that cites the professor’s recent papers and only your real projects. No auto-submit.

| ID | Sub-task | Status |
| --- | --- | --- |
| P2.1 | Domain: `ApplicationPacket`, requirements, professor papers, drafts | done |
| P2.2 | RCTCEOV prompts: requirements extract, eligibility checklist, evidence-bound drafts | done |
| P2.3 | Professor papers via OpenAlex (HTTP, no LLM) | done |
| P2.4 | Pipeline: vacancy extract → checklist vs profile/evidence → papers → CV / cover / proposal | done |
| P2.5 | API: prepare, get packet, list packets, list evidence | done |
| P2.6 | UI Prepare tab + Prepare button on opportunities | done |
| P2.7 | Tests: evidence-only drafts, mocked LLM, API contract | done |
| P2.8 | Lint + pytest (backend). Live UI if servers up | done |

Status values: `pending` · `in_progress` · `done`

## Gate checklist

- [x] Requirements extracted for a selected opportunity
- [x] Eligibility checklist (met / gap / unknown) against profile + evidence
- [x] Professor papers listed (or explicit empty if no supervisor/OpenAlex)
- [x] Tailored CV uses stored evidence only
- [x] Cover letter uses stored evidence only
- [x] Research proposal cites listed professor papers + stored evidence; no invented publications
- [x] Human still submits; no apply bot
