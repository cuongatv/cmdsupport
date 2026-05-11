# app/ai/ — LLM wiki compilation + provider abstraction

## OVERVIEW
Two layers:
1. **Provider wrappers** (`providers/`) — uniform async interface over Google Gemini, OpenAI, Anthropic, OpenRouter, and an internal `wtboss` provider. Each implements the contract in `providers/base.py`. The right wrapper is picked at runtime by `registry.py` from DB settings — **never** from env.
2. **Wiki agent pipeline** — converts uploaded sources into interlinked wiki pages by running an LLM tool-calling loop.

## PIPELINE (entry → exit)
```
arq worker (app/worker.py) — ingest_file_task / ingest_url_task
  └─ kb_service / source_outline.py     # extract text + image captions, build outline
  └─ wiki_analyzer.py                    # ONE cheap LLM call, returns structural plan
  └─ wiki_agent.py → compile_source_with_agent()
        ├─ wiki_agent_tools.py           # tool catalog: search_wiki / read_wiki_page /
        │                                #   create_page / update_page / append_log / finish
        ├─ agent_protocol.py             # tool-call <-> provider-message marshalling
        └─ wiki_compiler.py              # legacy compiler path (still imported in places)
```

## KEY FILES
| File | Role |
|---|---|
| `registry.py` | `ProviderRegistry` — resolves the active LLM/embedding/vision provider per call. **Always go through this; never instantiate a provider directly.** |
| `wiki_agent.py` | Agent loop. Top of file is the system prompt — that block is **a prompt, not code**. Edit prose, not Python. |
| `wiki_agent_tools.py` | Defines the `Tool` objects exposed to the LLM. Tool name = LLM-visible identifier; changing it is a breaking change for any in-flight runs. |
| `wiki_analyzer.py` | Pre-analysis (cheap, single call). Failures here MUST be soft — analysis is an optimization, not a gate. |
| `wiki_compiler.py` | Older single-shot compile path. New work belongs in `wiki_agent.py`. |
| `cmd_support_prompts.py` | BIDV CMD advisory prompt templates. Bilingual. |
| `agent_protocol.py` | Provider-neutral tool-call message format. Add a provider → implement the conversion here. |

## CONVENTIONS
- **System-prompt strings are content, not code.** Don't reformat them with autoformatters; don't dedupe with helpers. Treat them like markdown.
- **Wiki agent prompts forbid translation** of body content. Vietnamese stays Vietnamese, English stays English. Page *titles* may be normalized.
- **Add a provider** = new file in `providers/`, subclass `base.LLMProvider`/`EmbeddingProvider`, register the class in `registry.py`. Done — no other wiring needed.
- **Token counting / cost** belongs in the provider wrapper, not in the agent loop.

## ANTI-PATTERNS
- **Don't make `wiki_analyzer` block ingestion.** If it raises, log and continue with empty analysis.
- **Don't condense or summarize source content** in agent prompts — the explicit rule is "compile, do NOT summarize".
- **Don't hardcode provider/model names** outside `registry.py` and the provider wrappers. The whole point is runtime swap.
- **Don't add a tool to `wiki_agent_tools.py` and forget to wire it** into both the tool list AND the dispatcher in `wiki_agent.py` — silently no-ops otherwise.
