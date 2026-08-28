# Red Team Review — Phase 2, Milestone 1 Architecture

Reviewing `ops/reviews/cto-phase2-architecture.md` before Development.

## Overengineering / simpler-alternative check

**Static generator vs. live server: agree with CTO's rejection of a
server for this milestone.** Nothing here is interactive yet — a running
process would be pure overhead. Matches the existing `report.py`
pattern, which the Founder already trusts. No objection.

**A new `ops/control-center/` directory for one file — justified?**
Marginal by itself, but Phase 2 will grow more screens per `ROADMAP.md`
(Pipeline, Agents, Conversation, Meetings), and conflating a founder-
facing styled view with `report.py`'s git-tracked markdown output would
tangle two different consumers into one script. Accept the separate
module — **on the condition that nothing beyond `generate_overview.py`
is scaffolded now.** No empty `pipeline.py`/`agents.py` stubs "for
later." Build only what this milestone needs.

## Required before implementation (blocking)

1. **The `derived_state.py` extraction needs a regression test, not just
   a claim of behavioral equivalence.** CTO asserts report.py's output
   is unchanged after the refactor — prove it: capture `report.py`'s
   output against a fixed scratch database *before* the extraction,
   re-run *after*, diff byte-for-byte. QA must include this diff as
   evidence, not just re-run report.py once and eyeball it.
2. **HTML-escape every interpolated field, founder-authored content
   included.** Agree with CTO's flag, and extending it: this isn't only
   about malicious injection from an untrusted source — the Founder's
   own task titles or decision text could contain a stray `<` or `&`
   that silently breaks rendering (a robustness bug, not just a security
   one). `html.escape()` on every DB-sourced string, no exceptions, no
   "this field is probably safe."
3. **A non-functional affordance must look non-functional.** The
   Founder Inbox items render without live Approve/Reject — agreed. Go
   one step further: nothing on this page may visually imply an action
   that isn't wired (no button-shaped, hover-styled, or click-cursor
   element unless it does something). If there's any ambiguity whether
   an element reads as clickable, don't render it that way. This
   directly extends `CODING_STANDARDS.md` rule 23 (status must reflect
   persistent state, not fabricated activity) to capability, not just
   status.

## Alignment check

Confirmed against `DATA_MODEL.md` and `ARCHITECTURE.md`: read-only,
no new table, no `opsdb.py` write-path usage, `opsdb.py` remains the
only writer. No objection.

## Verdict

**PASS, conditional on items 1–3.** Development may proceed once the
regression diff is planned as part of QA (not optional), escaping is
applied universally, and no inert UI element is styled as actionable.
Scope stays to the Overview screen only — no additional screens or
scaffolding in this milestone.
