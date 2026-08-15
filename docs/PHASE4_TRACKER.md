# Phase 4 tracker — platform operations

**Done when:** a nightly job refreshes listings and a notification says
`N new >80% fits; M deadline in 7 days.`

n8n (or the CLI) owns the **clock**. Python owns discovery, scoring, tracking, and message text.
MCP tools are a permission boundary: validated arguments, no shell, no arbitrary SQL.

| ID | Sub-task | Status |
| --- | --- | --- |
| P4.1 | Tracker + ops rules (n8n has no business logic; notify is not an LLM) | done |
| P4.2 | Free LLMs (Groq, Ollama) never consume `LLM_DAILY_BUDGET_USD` | done |
| P4.3 | Domain: `NightlyDigest`, `Notification` | done |
| P4.4 | Deterministic digest: new high-fit + deadlines in 7 days | done |
| P4.5 | Nightly cycle: discovery → digest → notify (log + Telegram if configured) | done |
| P4.6 | MCP-style tools: DB read, local files list, digest preview (allowlisted) | done |
| P4.7 | API: tracker, digest, notifications, run-nightly, tools | done |
| P4.8 | n8n workflow JSON + compose profile (cron HTTP POST only) | done |
| P4.9 | UI Ops tab: digest, tracker, notifications, run now | done |
| P4.10 | Tests + backend API suite + live UI if servers up | done |

Status values: `pending` · `in_progress` · `done`

## Gate checklist

- [x] Nightly job can refresh listings (CLI and `POST /api/ops/nightly`)
- [x] Digest line matches `N new >80% fits; M deadline in 7 days.`
- [x] Telegram send is skipped (not failed) when token/chat is unset
- [x] n8n workflow only POSTs the API (no scoring in n8n)
- [x] MCP tools reject unknown names and invalid arguments
- [x] Groq/Ollama calls do not raise `BudgetExceeded`
- [x] Application tracking visible (packets, applications, deadlines)
