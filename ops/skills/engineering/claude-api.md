```
Skill name: claude-api
Purpose: Reference for the Claude API / Anthropic SDK — model ids, pricing, params, streaming, tool use, MCP, agents, caching, token counting, model migration.
When to invoke: Any architecture decision involving Claude/Anthropic model choice, integration, or LLM-shaped features with an unstated provider.
Inputs required: The specific question (pricing, model choice, limits, caching, etc.).
Analysis/checklist: Grounds the answer in current reference data rather than memory.
Expected output: Accurate, current answer to the API/model question.
Failure conditions: Question is about a different provider (OpenAI/Gemini/etc.) — out of scope for this skill.
Limitations: Reference only — does not select a model for an agent; that's the Model Registry's job (`/ops/models/`).
Which agents may use it: CTO/Architect Agent.
Version: as installed in this environment, 2026-08-28.
```
