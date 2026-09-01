# CURRENT_STATUS.md

Generated 2026-09-01 00:14 UTC by `ops/db/report.py` from the live database — do not hand-edit; re-run the script instead.

## Company Health: Good
1 task(s) blocked, 0 high-severity open risk(s)

## Completed
- TASK-001 — Verify Agent Pipeline
- TASK-002 — Phase 1: Data Model & Operational CLI
- TASK-004 — Phase 2 Milestone 1: DB-backed Overview generator
- TASK-005 — Phase 2 Milestone 2A: Pipeline, Agents, Decisions, Meetings screens
- TASK-006 — Phase 2 Milestone 2B1: Founder Inbox Approve/Reject/Discuss write path
- TASK-007 — Phase 2 Milestone 2B2: real Ask-Agent + persistent conversations
- TASK-009 — Phase 2 Milestone 2B3A: controlled concurrent Agent Runtime foundation
- TASK-010 — Phase 2 Milestone 2B3B: real Executive Meetings
- TASK-011 — Phase 2 Milestone 2B3B round 2: Executive Meetings correction (Orchestrator selection, request-perspective, follow-up, retry)
- TASK-012 — Chief of Staff rename
- TASK-013 — Phase 2 Milestone 2B4: Founder Identity Verification for Consequential Write Actions
- TASK-014 — Phase 2 Milestone 2B5: Review/QA Failure History & Release Readiness Visibility
- TASK-015 — Phase 3A: Chief of Staff Founder Interface + Limited Automated Orchestration

## In progress
- TASK-016 — Risk id=3 architecture investigation: can agent access be scoped below the Bash tool-category level (FOUNDER_APPROVAL, owner: orchestrator, progress: not broken into steps)
- TASK-018 — Product architecture completion review: remaining Phase 3, Founder Work Progress capability, Founder Test Readiness definition, ROADMAP correction (ARCHITECTURE, owner: cto, progress: not broken into steps)
- TASK-019 — Milestone A: Active Work dashboard + Task Detail page (QA, owner: qa, progress: not broken into steps)

## Blocked
- TASK-017 — Risk id=3 reduction milestone: reviewer zero-tool rollout + self-immune Developer denylist: no reason recorded

## Waiting (Backlog)
- none

## QA failures (unresolved)
- TASK-019 — Milestone A (TASK-019) user-perspective QA: malformed task IDs, all 17 real tasks, Active Work dashboard (sort/exclude-DONE/zero-active), unauthenticated access, stuck-badge and Project-field fix verification, navigation/dead-anchor fixes, regression on pipeline/releases/automation/reviews, concurrency, server restart: gates_completed()/render_gate_timeline() mislabel the task's own CURRENT gate as DONE whenever that gate was previously entered-and-exited-backward (a reject/rework loop) and the task has since re-entered the identical gate a second time. Root cause: gates_completed()'s SQL only checks whether ANY later task_status_history row exists whose to_status is a ladder position -- it does not check that the later row represents a genuinely FORWARD exit (i.e., a higher GATE_STATUS_ORDER index than the row being evaluated). A backward transition (e.g. a Code Review REJECT moving CODE_REVIEW -> IN_DEVELOPMENT) still satisfies this EXISTS check and wrongly marks the exited-from gate as completed. When the task is later resubmitted back into that same gate, render_gate_timeline() checks 'status in completed_set' before 'status == effective_status', so the live, current gate renders with a green DONE pill and check-mark instead of the amber CURRENT ring -- and the page shows NO CURRENT marker anywhere at all. Reproduced live on TASK-019 itself (this milestone's own tracking task): tasks.status='CODE_REVIEW' (confirmed via SELECT), effective_gate_status()='CODE_REVIEW', but 'CODE_REVIEW' in gates_completed() is also True, so /tasks/19.html's Gate timeline renders every single gate row as DONE or WAITING with zero CURRENT entries, hiding that the task is presently, live, sitting in Code Review awaiting outcome. Independently reproduced by calling ops/db/derived_state.gates_completed()/effective_gate_status() directly against the scratch clone's copy of the live DB (task_status_history rows 139 CODE_REVIEW entered, 140 CODE_REVIEW->IN_DEVELOPMENT reject, 141 IN_DEVELOPMENT->CODE_REVIEW resubmit -- current, unexited). This is not a rare edge case: reject-then-fix-then-resubmit into the identical gate is an ordinary, expected outcome of this system's own Code Review/QA/Security gates (DEC-009's own 8-step sequence), and it already happened on this milestone's own real data during its own Code Review round. Directly contradicts the design's own explicit requirement (cto-milestone-a-architecture.md Part 4.2 item 2: gate timeline entries rendered DONE/CURRENT/WAITING) and defeats the page's core purpose of showing what gate a task is live at right now. Fix should mirror the same evidenced-not-assumed discipline already applied to gates_remaining() (Red Team's high-water-mark fix): gates_completed()'s EXISTS subquery needs to additionally require GATE_STATUS_ORDER.index(h2.to_status) > GATE_STATUS_ORDER.index(h1.to_status), or equivalently exclude effective_status itself from the completed set at the point of rendering DONE/CURRENT/WAITING (CURRENT check should take precedence over a stale completed_set entry for the task's own current gate). (returned to developer)

## Current risks (open)
- [medium] Bash permissions cannot be scoped below the tool-category level (company, owner: cto)

## Founder decisions required
- TASK-016 — Risk id=3 architecture investigation: can agent access be scoped below the Bash tool-category level is waiting at FOUNDER_APPROVAL

## Agents
- ceo: available
- Chief of Staff: available
- code-review: available
- cto: available
- design: available
- developer: available
- devops: available
- financial: available
- marketing: available
- product: available
- project-manager: available
- qa: available
- red-team: available
- security: available

