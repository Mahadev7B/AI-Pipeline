# Skill Registry

Skills are **tools** an agent uses — see `AGENT_ARCHITECTURE.md`. They never
replace an agent's role, must-not list, or evaluation criteria.

This registry is populated only with Claude Code skills actually confirmed
installed in this environment as of Phase 0 (2026-08-28). Do not add an
entry for a skill you haven't verified exists. Re-check this list whenever
the installed-skills set changes and update entries accordingly.

## Categories

```
/ops/skills/
  engineering/   code-review, simplify, run, init, claude-api
  security/      security-review
  design/        design
  product/       prompt-master
  operations/    update-config, fewer-permission-prompts, loop, skill-creator
```

Each entry uses `SKILL_TEMPLATE.md`'s field set.

## Agent → Skill map

| Agent | Skills used | When |
|---|---|---|
| Chief of Staff | `prompt-master`, `skill-creator`, `loop` | precise handoff instructions; maintaining this registry; Phase 3 recurring checks |
| Product | `prompt-master` | turning a rough idea into a precise brief |
| Design | `design` | producing real mockup artifacts |
| CTO/Architect | `init`, `claude-api` | codebase docs bootstrap; Claude/Anthropic API integration decisions |
| Red Team | — | pure reasoning/checklist role, no tool skill |
| Developer | `run`, `simplify` | verifying a change works; post-implementation cleanup |
| Code Review | `code-review` | reviewing a diff |
| QA | `run` | driving the real app to test |
| Security | `security-review` | reviewing pending changes |
| DevOps | `update-config`, `fewer-permission-prompts` | environment config; session hygiene |
| Marketing | — (see note) | |
| Project Manager | — | |
| CEO | — | operates through frameworks, not a tool skill |
| Financial | — | operates through frameworks, not a tool skill |

## Not currently mapped to a specific agent

`dataviz`, `artifact-design`, `artifact-diagramming`, `artifact-capabilities`,
`docx`, `pdf`, `pptx`, `xlsx`, `keybindings-help`, `morning`,
`import-memory`, `session-start-hook` are installed but have no clean
one-agent mapping yet. Available on demand rather than forced into the
table above — e.g. `docx`/`pptx` for a Marketing one-pager or deck,
`dataviz` for whoever builds the Phase 2 Control Center's status
visualizations. Do not pre-assign these; map them when a real task
actually needs one.

## How a skill earns trust (policy — not executed in Phase 0)

1. Define the skill's expected behavior.
2. Create benchmark scenarios for it.
3. Run the skill against them.
4. Have another agent evaluate the results.
5. Record known limitations.
6. Version the skill entry.
7. Improve it when a failure is discovered; re-benchmark after a material
   change.

Agents use only the skills relevant to the task at hand — never every
installed skill "just in case."
