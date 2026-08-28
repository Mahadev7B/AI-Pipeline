# CODING_STANDARDS.md — Shared Engineering Rules

All agents follow these rules. No agent is exempt, including CEO and
Financial.

1. Never code before requirements and acceptance criteria exist.
2. Prefer the simplest solution that satisfies the requirement.
3. Do not introduce dependencies without explaining why.
4. Do not make architecture changes silently.
5. Do not perform unrelated refactoring during a feature.
6. Never claim something works without testing it.
7. The agent that creates something cannot be the final approver of its own
   work.
8. Failed QA returns to Development.
9. Significant fixes must pass Code Review again.
10. Important decisions must be documented in `DECISIONS.md`.
11. Never spend money without Founder approval.
12. Never expose credentials or secrets.
13. Never modify production outside the explicit release process.
14. Meaningful deployments always have a rollback path.
15. If information is uncertain, investigate instead of inventing an answer.
16. Do not build features merely because they might be useful someday.
17. Keep MVP scope small.
18. Agents should disagree when appropriate — consensus is not the goal,
    a correct decision is.
19. Review agents actively search for mistakes; they do not rubber-stamp.
20. Always preserve Git history.
21. Never bypass a failed review without resolving it.
22. Progress percentages must reflect real completed work or defined
    subtasks — never an arbitrary guess.
23. Status shown anywhere (docs or, from Phase 2, the Control Center) must
    reflect persistent system state, not fabricated "live activity."
24. Agent conversations and decisions must be auditable — recorded, not
    just said in passing.
