```
Skill name: run
Purpose: Launch and drive the project's app to see a change working in the real app (not just tests).
When to invoke: Developer confirming a change works; QA testing real behavior before pass/fail.
Inputs required: A running/runnable project.
Analysis/checklist: Project-type detection (CLI, server, TUI, Electron, browser-driven, library); prefers an existing project launch skill if one exists.
Expected output: The app running, with observed behavior (and a screenshot where applicable).
Failure conditions: App won't start; no known launch pattern for the project type.
Limitations: Confirms the app runs and behaves as observed — not a substitute for QA's full edge-case checklist.
Which agents may use it: Developer Agent, QA Agent.
Version: as installed in this environment, 2026-08-28.
```
