# Founder Directive — TASK-024 Scope Correction: Multi-Agent Idea Deciphering + Founder UI

**Received 2026-09-01. Reproduced verbatim below, unedited.** This is the authoritative
input for Product's revision and Design's revised mockup. Where any summary of this
directive (including DEC-014's) differs from the text below, the text below governs.

Preserving the Founder's raw words unaltered is itself the principle this feature
encodes: raw Founder idea is never overwritten by anyone's interpretation of it.

---

TASK-024 Founder Scope Correction — Multi-Agent Idea Deciphering + Founder UI

The Founder should NOT be expected to provide a perfect prompt or product specification.

The Founder may type a raw idea in normal language — short, messy, incomplete, uncertain, or conversational.

The AI Factory must decipher and brainstorm the idea BEFORE it becomes an executable project.

IMPORTANT:
Raw Founder idea ≠ final implementation prompt.

==================================================
1. RAW IDEA
==================================================

Founder enters an idea in their own words.

Preserve the original raw idea exactly.

Founder can choose:

[ Save Idea ]
[ Refine / Brainstorm ]

Save Idea:
- saves the idea only
- no agents start execution
- no downstream build begins
- no implementation spend begins

==================================================
2. MULTI-AGENT DECIPHERING / BRAINSTORMING
==================================================

Use the existing brainstorming skill where appropriate.

Product is the lead deciphering role.

Chief of Staff selects additional agents based on the idea.

Possible participants:

PRODUCT
- What problem is the Founder actually trying to solve?
- Who is it for?
- What outcome matters?
- What is the smallest useful version?
- What requirements are implied?

CEO
- Does the idea make strategic/product sense?
- Are we solving the right problem?
- Is there a better or simpler direction?
- What outcome should the company optimize for?

CTO
- Is it technically realistic?
- Are there important technical constraints?
- Is there a simpler technical direction?
- Are we making dangerous assumptions?

RED TEAM
- What might the company be misunderstanding?
- What assumptions should be challenged?
- Why might this fail?
- Are we solving the wrong problem?
- Is there a simpler alternative?

DESIGN
Use when UX is important.
- What should the user actually experience?
- What interaction assumptions need clarification?

SECURITY / PRIVACY
Use only when genuinely relevant.

FINANCIAL
Use only when cost, pricing, budget, or viability materially affects the idea.

Do NOT automatically use every agent.

Chief of Staff should choose only the perspectives that materially improve understanding.

==================================================
3. DECIPHER BROADLY, COMMUNICATE NARROWLY
==================================================

Agents may debate internally.

Do NOT dump separate Product, CEO, CTO, Red Team reports on the Founder.

Chief of Staff synthesizes everything into ONE Founder-facing response:

WHAT I THINK YOU MEAN

WHAT YOU ARE REALLY TRYING TO ACHIEVE

MY RECOMMENDED DIRECTION

IMPORTANT ALTERNATIVES

ASSUMPTIONS WE ARE MAKING

WHAT I NEED FROM YOU

Ask the Founder only questions that can materially change direction.

Do not ask questions agents can reasonably decide themselves.

==================================================
4. CREATE THE INTERPRETED PROJECT BRIEF
==================================================

Convert the raw idea + brainstorming into a clean project brief.

Include where relevant:

- Product/project name
- Original Founder idea
- Problem/opportunity
- Goal
- Target user
- Desired experience
- Recommended initial scope
- Core requirements
- Constraints
- Assumptions
- Alternatives considered
- Out of scope
- Risks/uncertainties
- Open Founder decisions
- Success criteria

Use plain language first.

==================================================
5. FOUNDER REVIEW GATE
==================================================

Show the interpreted brief to the Founder BEFORE execution starts.

Founder-facing actions should include:

[ Brainstorm More ]
[ Refine ]
[ Edit ]
[ Approve Brief ]

Founder must be able to correct the company's interpretation.

Do not allow downstream execution until the brief is approved.

==================================================
6. START WORK
==================================================

After Founder approval, provide a separate consequential action:

[ Approve Brief & Start Work ]

This is the action that begins actual execution.

Clearly communicate before the click:

- AI agents will begin working
- real AI cost may be incurred
- the approved brief becomes the authoritative project instruction

The raw idea must NOT be sent downstream as the implementation prompt.

The Founder-approved brief becomes the source of truth.

==================================================
7. AUDIT TRAIL
==================================================

Preserve all three versions separately:

RAW FOUNDER IDEA
        ↓
AI-INTERPRETED / BRAINSTORMED BRIEF
        ↓
FOUNDER-APPROVED BRIEF

Never overwrite one with another.

The company must always be able to answer:

- What did the Founder originally say?
- What did the AI company interpret?
- What did the Founder actually approve?

==================================================
8. REQUIRED UI / MOCKUP CHANGES
==================================================

THIS IS A FOUNDER-FACING UX CHANGE, NOT ONLY A WORKFLOW CHANGE.

Update the TASK-024 mockup.

The revised UI must visibly demonstrate:

Raw Idea
    ↓
Save / Refine
    ↓
Brainstorming / Deciphering
    ↓
Chief of Staff Synthesis
    ↓
Clarification if necessary
    ↓
Interpreted Brief
    ↓
Founder Review
    ↓
Founder Approval
    ↓
Approve Brief & Start Work
    ↓
Factory Starts Working

The mockup must show:

1. Raw idea entry screen
2. Save Idea button
3. Refine / Brainstorm button
4. What the Founder sees while deciphering happens
5. Which company perspectives participated, without dumping raw agent output
6. Chief of Staff synthesis
7. Assumptions
8. Important alternatives
9. Clarifying questions when required
10. Interpreted project brief
11. Brainstorm More / Refine / Edit controls
12. Approve Brief
13. Approve Brief & Start Work
14. Clear warning that Start Work begins execution and may incur AI cost
15. What the Founder sees immediately after the factory begins working

Do NOT consider Design complete because individual screens look attractive.

The entire Founder journey must be visually coherent and clickable/walkable.

==================================================
9. COMPANY PRINCIPLE
==================================================

Think of this like a real software company.

Founder:

"I have this idea..."

Product, CEO, CTO, Red Team and other relevant leaders think about it internally.

Chief of Staff returns:

"Here is what we believe you mean.
Here is what you're actually trying to achieve.
Here is what we recommend.
Here are the assumptions we made.
Here is the one decision we still need from you."

Founder corrects or approves.

ONLY THEN does the company execute.

==================================================
10. PROCESS
==================================================

Record this as a Founder scope correction to TASK-024.

Product must revise the brief first.

Then Design must revise the mockup.

Do not proceed to implementation until the deciphering + Founder approval UX is visually coherent and Founder-approved.

This does NOT authorize unattended automatic pipeline execution.

Founder remains the authority who deliberately starts work.
