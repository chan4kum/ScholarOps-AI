# Agent rules for this repo

Product name: **ScholarOps AI**. Python package remains `opportunity_intel`.

- Local-first. Do not send raw HTML to paid LLMs.
- Agents call `LLMRouter.complete(role)`, never vendor SDKs.
- Every agent prompt uses R-C-T-C-E-O-V (Role, Context, Task, Constraints, Examples, Output, Verification) in `opportunity_intel.llm.prompting`.
- Default chat model: `deepseek-v4-flash` (not retired `deepseek-chat` / `deepseek-reasoner`).
- Groq is for fast extract (`openai/gpt-oss-20b`). Polish is opt-in.
- Hugging Face token is for embeddings/model download, not chat.
- Geography: worldwide. Do not exclude UK/GB. Empty `target_countries` / `excluded_countries` means no country filter. Drop listings that are not PhD vacancies, not countries.
- CV/proposal text may only use stored evidence. Do not invent credentials.
- Application submit requires a human approval token (HMAC, expiring, single-use). Pause before send.
- Apply as the user after that one confirmation: pathfind email vs public portal, then SMTP or Playwright. Live send needs `APPLY_AS_ME=true`. Never university passwords, CAPTCHA solving, or payment.
- `sandbox` is a local fake portal. `manual` only logs. Never generic remote HTTP POST (`http_form` is loopback-only).
- Groq and Ollama are free: they must not consume `LLM_DAILY_BUDGET_USD`. Paid DeepSeek still does unless the budget is `<= 0`.
- n8n may only trigger `POST /api/ops/nightly`. Digest text and Telegram send live in Python.
- Ops MCP-style tools are allowlisted (`db.*`, `files.list_import_dir`, `notify.preview_digest`). No shell or arbitrary SQL.
- Never commit `.env` or API keys.
- When debugging agents, read `data/logs/agent-runs.jsonl` and `GET /api/monitor/health`.
  Failed runs include agent name, action, error, duration, and LLM spans (no secrets).
