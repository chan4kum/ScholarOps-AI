# LLM routing and cost control

## Decision

You have **Groq** (fast open models), not xAI Grok.

| Default | When | Cost posture |
| --- | --- | --- |
| No LLM | Parsing, eligibility rules, dedupe | Free |
| Groq `extract` | HTML/main-text → JSON via `openai/gpt-oss-20b` | Cheap / free-tier friendly |
| DeepSeek `reason` | Fit scores — `deepseek-v4-flash`, thinking off | Cheap API |
| DeepSeek `draft` | Proposal / SOP — same model, thinking on | Cheap; avoid `deepseek-v4-pro` |
| Groq `polish` | Toggle `GROQ_POLISH_ENABLED` | Off by default |
| Hugging Face `embed` | `BAAI/bge-small-en-v1.5` | Phase 2+ |
| Ollama `fallback` | APIs down | Free, local |
| OpenAI (optional) | `reason`/`draft` if DeepSeek key missing | `gpt-5-nano-2025-08-07` |
| Gemini (optional) | Discovery Search grounding | `gemini-2.5-flash`; not used by agent files |

## Discovery search order

1. EURAXESS + AcademicTransfer RSS (no LLM)
2. FindAPhD HTML parse (no LLM)
3. DuckDuckGo (free, no key)
4. Brave Search if `BRAVE_API_KEY` is set
5. Tavily if still below `DISCOVERY_MIN_RESULTS` and `TAVILY_API_KEY` is set
6. Fetch pages with httpx (Playwright only if `USE_PLAYWRIGHT=true`)
7. Local extract (JSON-LD, trafilatura, regex)
8. Groq `extract` **only** when local extract is thin — never Grok on HTML

Per discovery run, per opportunity:

1. `extract` (local) — requirements JSON  
2. `reason` (DeepSeek) — fit score + 5-bullet rationale — **only if** rule eligibility passed  

No draft calls in Phase 1.

## Kill switches

- `LLM_DAILY_BUDGET_USD` (paid providers only; `<= 0` disables). Groq and Ollama never count.  
- `GROK_ENABLED=false` by default  
- `OFFLINE=true` → Ollama only, skip drafts  
