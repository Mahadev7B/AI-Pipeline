# Claude → Founder

Replies from the build side, updated as work lands. Newest first.

---

## 2026-09-04 — Founder direction: Full-depth Idea Desk research must actually search the web when outside facts can change the recommendation

The Founder ran the Idea Evaluator again after the market-research guidance was strengthened, and the evaluation still said that no research was performed and that nobody could browse the web.

This is now clearly **an implementation/capability gap, not another prompting problem**.

The current evaluator tells the agents that no agent can browse the web, and the Idea Evaluation runtime deliberately invokes Claude with zero built-in tools and zero MCP tools. That means the company can identify what should be researched, but it cannot actually perform the research. Telling Product/CTO/Chief of Staff to “broaden market research” cannot fix a runtime that has no research capability.

### Required product correction

For a **Full-depth** Idea Desk evaluation, when current external facts could materially change the product thesis, architecture, market opportunity, pricing, platform feasibility, legal/privacy assumptions, competitor differentiation, or recommendation, the Factory should include a real **Research lane** before final convergence.

Conceptually:

`Founder idea`

→ Product/Design infer the real outcome

→ CTO generates the materially different solution / architecture categories worth testing

→ **Research lane searches the real world across those categories**

→ Product + CTO reconsider the solution using the evidence

→ Red Team attacks the evidence-backed provisional direction

→ relevant roles repair / re-enter if new domains appear

→ Chief of Staff synthesizes the final recommendation

The important change is that research becomes **evidence consumed by the company before synthesis**, not a sentence saying “someone with a browser should check this later.”

### Research should be a bounded, read-only capability — not broad tool access for every agent

Do **not** solve this by giving Product, CTO, Red Team, Security, and Chief of Staff unrestricted Bash / filesystem / arbitrary tool access.

Preserve the current least-privilege model for ordinary evaluation agents. Add a narrowly scoped research capability or dedicated Research lane whose job is to retrieve public information and return an evidence packet.

The lane should be read-only with respect to the repo and local machine. It should not be able to edit code, deploy, spend money, create accounts, or take external actions merely because research is needed.

If the safest architecture is a deterministic web-search/retrieval service rather than a new human-like agent identity, that is acceptable. The requirement is **real external evidence**, not adding another persona for its own sake.

### Do not silently change the Founder's billing/provider model

The Factory currently runs Idea Evaluation through Claude Code / the Founder's existing Claude plan. Do not silently switch evaluation to a pay-as-you-go API, add an API key, enable a separately billed search provider, or incur new paid-service charges merely to obtain web research.

First determine whether the existing Claude Code / Max path can safely expose a web-only research capability while keeping Bash/Write/Edit disabled. If a separate paid API, search provider, account, or other new spend is genuinely required, that is a Founder approval decision and should be surfaced before enabling it.

### Full-depth research standard

The prior Founder direction still applies: research must **broaden the search and check every meaningful solution class**, not inspect the first few obvious competitors.

For each Full-depth idea where outside facts matter, the research lane should start from the desired outcome, not just the product name, and systematically cover:

- direct competitors,
- substitutes,
- adjacent products,
- alternative technical architectures,
- relevant hardware / integrations / APIs,
- products delivered through less-obvious channels,
- pricing and business models,
- user reviews and recurring complaints,
- failed or discontinued approaches where useful,
- platform constraints,
- current legal/privacy/regulatory facts when they materially affect the recommendation,
- and counterexamples that could invalidate the company's preferred solution.

Search using multiple terms and angles. When research reveals a new solution category that could materially change the answer, expand into that category before synthesis. Stop on a practical diminishing-return rule: when additional searches are no longer revealing materially new solution classes, important competitors/substitutes, or evidence that changes the ranking.

For the medication idea, a real research sweep should have included categories such as:

- smart medication caps / connected bottles,
- retrofit bottle sensors,
- BLE / motion / magnetic sensing that could be repurposed,
- smart pillboxes and dispensers,
- NFC medication workflows,
- medication reminder and adherence apps,
- pharmacy / insurer / health-system adherence products,
- caregiver monitoring / remote patient monitoring,
- user complaints about batteries, pairing, setup, refills and false signals,
- pricing and availability,
- discontinued products,
- and why existing connected-medication products have or have not become effortless/mainstream.

The key question remains broader than “does a smart cap exist?” It is:

> **What are all the materially different ways this outcome is already being solved, why have those approaches succeeded or failed, and what does that evidence tell us about the strongest architecture?**

### Evidence packet requirements

The synthesis should not receive an untraceable paragraph called “market research.” The Research lane should return a compact, auditable evidence packet containing, where applicable:

- source title / organization,
- source URL or stable reference,
- date accessed / publication date when relevant,
- what factual claim the source supports,
- which solution category it belongs to,
- important pricing / capability / constraint facts,
- notable user complaint or adoption evidence when used,
- contradictions between sources,
- what remains unknown,
- and which findings materially changed (or did not change) the architecture ranking.

The final Founder-facing page does not need to dump every source, but it should be able to show the evidence behind claims and distinguish **verified current fact** from company reasoning/recollection.

### Research must be allowed to change the roster and the solution

Research is not a box to check after the company has already decided.

If research discovers, for example, that a cheap finished smart cap already exists with an accessible integration path, CTO should be allowed to re-rank the architecture and possibly replace the provisional retrofit-sensor plan.

If research discovers that the category's real failure is pairing/battery/setup rather than sensor accuracy, Design and Product should re-enter.

If it introduces sensitive data, regulated claims, or another risk domain, Security/other relevant roles should re-enter dynamically.

The required pattern is:

`form solution space → gather real evidence → update solution space → challenge → repair → synthesize`

not:

`pick solution → write “research needed” → synthesize anyway`.

### Acceptance standard

Before calling Full-depth research support complete, please prove at least these behaviors with deterministic tests/rehearsals plus one controlled real run when appropriate:

1. A Full-depth idea whose recommendation depends on current market facts triggers the Research lane.
2. A Light-depth idea that does not need external facts does not browse just because browsing exists.
3. Evaluation agents still do not gain Bash/Write/Edit merely because research exists.
4. Research evidence is preserved and attributable rather than converted into unsupported prose.
5. Chief of Staff can distinguish verified external facts from inference/recollection.
6. A research finding can cause CTO/Product to re-rank or reopen the solution, instead of being ignored after the provisional architecture is chosen.
7. Newly discovered material categories can expand the research sweep before final synthesis.
8. Search is bounded; there is no unbounded research loop.
9. No new paid provider/API/search spend is silently enabled.
10. If research capability is unavailable, the evaluation fails honestly or explicitly downgrades to “research unavailable”; it must not pretend that a Full-depth market scan occurred.

### Founder intent

The Founder wants the Idea Evaluator to behave like a real product company doing diligence before recommending what to build. A Full-depth evaluation should not repeatedly say “nobody here can browse” while simultaneously making market and architecture judgments that depend on current external facts.

Please treat this as a requested **Idea Desk product capability correction**: make research executable and evidence-backed, while preserving least privilege and existing approval/spend boundaries. It is not authorization to broaden every agent's tools, switch billing models, incur new paid-service charges, or bypass normal independent review/production gates.

---

## 2026-09-03 — Company View correction: do not let an agent-invented differentiator redefine the opportunity

The Founder reviewed the **Company view** from the latest medication evaluation and sees a deeper synthesis problem that should be corrected in future Idea Desk runs.

The Company view says:

> “the differentiator and the biggest risk are the same thing: telling another person you missed a dose.”

That is a coherent description of the company’s **chosen social-accountability architecture**, but it is not a neutral description of the Founder’s original product opportunity. The Founder’s distinctive insight was physical/action evidence: a reminder should know whether the person actually interacted with the medication, rather than merely whether a notification was delivered or a button was tapped.

### 1. Do not silently promote an internally invented tactic into “the differentiator”

The evaluation moved through this chain:

`Founder insight: notification is not evidence of action`

→ company invents social escalation

→ company calls social escalation “the entire differentiator”

→ company rates the opportunity Medium because that internally invented differentiator may be legally constrained.

That is too much conceptual drift.

A company is allowed — and expected — to improve or even replace the Founder’s proposed implementation. But if it changes the **product thesis**, the synthesis must say so explicitly and justify the change.

For example:

> “The Founder’s original differentiator is physical evidence of medication interaction. We considered that seriously. We are recommending social accountability instead because A/B/C evidence shows physical sensing is inferior on user friction, feasibility and market opportunity.”

Without that explicit bridge, the Company view can end up grading a different idea from the one the Founder brought in.

### 2. There is an internal contradiction in the current Company view

The evaluation correctly says, under **Biggest merit**, that the Founder’s cap instinct identified a real problem because:

> a tap on a screen proves nothing.

But the chosen “Best differentiation” then returns to a lock-screen **Taken / Not yet tap** and makes social escalation the main mechanism.

In simplified form:

`diagnosis: a tap is weak evidence`

`chosen product: use a tap, then add social pressure`

That may still be a useful architecture, but it does **not** solve the evidence problem the company itself identified. The Company view should surface that trade honestly rather than present the replacement as though it preserved the same differentiator.

### 3. Do not manufacture a single point of failure and then use it to downgrade the whole opportunity

The company says legal restrictions on third-party escalation could “kill” the project because escalation is “the entire differentiator.” But escalation became load-bearing only because the company chose to make it load-bearing.

That creates a bad evaluation pattern:

`choose one architecture → make one feature essential → discover that feature is risky → lower the opportunity rating`

Instead, separate these judgments:

- **Problem / outcome opportunity:** is there a meaningful unmet need around missed doses, uncertain doses, and evidence of medication interaction?
- **Solution-space quality:** are there multiple credible ways to address it?
- **Recommended architecture:** which solution currently looks strongest?
- **Architecture-specific blocker:** what could kill this particular implementation?

A blocker to one architecture should not automatically become a blocker to the underlying opportunity when other credible architectures remain unexplored.

### 4. “Reminders that carry no consequence” is not the same problem framing as the Founder’s

The current Company view reframes the gap as:

> reminders that carry no consequence.

That pushes the product toward **pressure / accountability**.

The Founder’s framing is closer to:

> reminders that are not aware of whether the real-world action occurred.

That pushes the product toward **action-awareness / evidence**.

Those are different product philosophies:

`social-accountability framing: no response → increase pressure`

`action-aware framing: no physical evidence → continue helping / escalate appropriately`

The company should be very careful when changing an outcome-level framing, because every later architecture choice follows from it.

### 5. “Connected cap = nine months and a different company” is too broad unless the tournament and research prove it

That statement may be reasonable for **designing, manufacturing, certifying and supporting a custom connected medical cap from scratch**.

It does not establish that **physical sensing generally** is a nine-month hardware-company commitment.

CTO and market research must distinguish at least:

- custom manufactured smart cap,
- existing commercial smart-cap integration,
- off-the-shelf BLE sensor,
- reusable retrofit sensor,
- Hall/magnetic open-close sensing,
- accelerometer / rotation sensing,
- NFC interaction,
- smart pillbox / compartment sensing,
- weight or presence sensing,
- hybrid automatic + manual evidence.

The architecture tournament should determine whether physical sensing is actually impractical before the Company view writes it off as a different company.

### 6. Opportunity rating should survive architecture changes

A useful Company view should be able to say something like:

> **Opportunity: Medium–High, pending market research and evidence-sensing feasibility.** The underlying gap is between digital reminders and trustworthy evidence of real-world medication interaction. Several architecture classes may address it. Social escalation is one candidate, not the definition of the opportunity.

Then separately:

> **Current recommended architecture:** [X]

> **Biggest architecture-specific threat:** [Y]

That prevents the opportunity score from being held hostage by whichever implementation happened to win one internal round.

### 7. Add a synthesis check before writing the Company view

Before Chief of Staff writes **Opportunity / Biggest merit / Biggest threat / Best differentiation / Recommendation**, it should explicitly verify:

1. What was the Founder’s original core insight?
2. What is the company’s improved product thesis?
3. Are those still the same thesis?
4. If not, why did the company change it?
5. Did CTO seriously explore architectures that preserve the original insight?
6. Did market research broadly test both the Founder’s direction and the company’s alternative?
7. Is the stated “biggest threat” a threat to the **opportunity**, or only to the **chosen architecture**?
8. Does “Best differentiation” actually solve the problem described under “Biggest merit,” or did the company quietly substitute a different mechanism?

If those cannot be answered cleanly, the Company view is converging too early.

### Desired standard

The strongest version of this Company view would say something closer to:

> **The opportunity is not simply better medication reminders or notifying a family member. The opportunity is closing the gap between a digital reminder and evidence that a real-world medication interaction occurred. We evaluated multiple ways of obtaining that evidence and multiple ways of responding when it is absent. Here is the architecture that survived, why it beat the others, and what still has to be proven.**

That is the standard the Founder wants: improve the idea aggressively, but do not lose track of which problem and differentiator are being evaluated.

This is additional Founder product-direction feedback for the Idea Desk synthesis behavior. It reinforces the prior directions on **invent first → challenge → improve**, architecture tournaments, and broad market research. It is not authorization to bypass any standing approval, privacy, review, or production gates.

---

## 2026-09-03 — Founder feedback: preserve the physical-sensing insight, and make market research broad enough to challenge the whole solution space

The Founder compared the latest **Proof-of-dose medication reminder** evaluation with an independent ChatGPT evaluation. The latest company run is materially better than the earlier Idea Desk behavior — it generated alternatives, dynamically brought Security in, and resolved more forks internally — but the Founder wants one important correction in how the company protects the core insight of an idea while transforming it.

### 1. Do not optimize away the most distinctive part of the Founder’s idea before proving it is impractical

The Founder’s original insight was not simply “send a stronger medication reminder.” It was:

`remind → detect a real-world medication interaction → respond when that interaction does not happen`

The bottle-cap / physical-sensing concept matters because a normal reminder app only knows that a notification was delivered. The Founder is trying to create independent evidence that the person actually went to the medication.

The latest evaluation moved quickly toward a thin app + social escalation and postponed physical sensing. That may eventually be the right decision, but the company should not remove the physical-action differentiator before CTO has seriously tried to make it cheap, simple, and reversible.

A better product framing is:

> **A medication reminder that watches for real-world evidence that the user interacted with the medication container, and acts when that evidence does not appear.**

Be precise about the evidence: a cap opening does **not** prove ingestion. Store and communicate the event honestly as something like “bottle opened at 8:04 AM,” and only derive a qualified state such as “likely taken” if the product chooses to infer it.

### 2. Run a genuine architecture tournament around physical evidence

For this idea, CTO should compare materially different evidence architectures before converging. At minimum, consider categories such as:

- ordinary app self-report,
- NFC / tap-to-confirm,
- Bluetooth smart cap,
- reusable retrofit bottle sensor,
- smart pillbox / compartment sensing,
- camera / computer vision,
- hybrid designs where automatic sensing is primary and NFC/manual confirmation is fallback.

Do not treat these as a checklist with a preselected winner. Compare them on:

- automatic vs manual user effort,
- evidence quality,
- false-positive / false-negative behavior,
- hardware cost,
- setup burden,
- battery life,
- compatibility with common medication containers,
- reliability when the phone is unavailable,
- time to prototype,
- manufacturability / certification burden,
- reversibility,
- privacy exposure,
- scalability,
- and whether the architecture keeps a path open to better evidence later.

A particularly important candidate to investigate is a **reusable retrofit sensor** rather than immediately assuming a custom manufactured cap. The company should ask whether a small sensor using cap separation, rotation, acceleration, magnetic/Hall sensing, or another simple physical signal can attach to existing bottles and report events over Bluetooth. This is not a direction to preselect that design; it is a direction to search harder for ways to preserve the Founder’s core insight without prematurely turning the company into a nine-month hardware program.

### 3. Design the system around evidence levels, not a single “Taken” boolean

The data model and product reasoning should be able to distinguish evidence sources such as:

`self-report → NFC interaction → bottle-open event → caregiver confirmation → stronger future evidence`

That makes hardware evolution additive rather than a rewrite and avoids dishonest claims.

The product should also understand context. A bottle opening near a scheduled dose window is different from a bottle opening hours later to refill an organizer. Architecture and Product should reason about confidence, not collapse all activity into “taken.”

### 4. The interesting user outcome may include duplicate-dose uncertainty, not only missed doses

The Founder’s idea may solve two problems:

- “I forgot to take it.”
- “I cannot remember whether I already took it.”

The second can be a powerful wedge. The company should test whether reducing **dose uncertainty** is as important as reducing missed doses, rather than assuming reminder adherence is the only outcome.

### 5. Recommendation quality: preserve the sensing direction unless evidence defeats it

For this evaluation, ChatGPT’s alternative recommendation was closer to:

**Proceed with narrowed scope** — prototype software + automatic bottle-interaction sensing using inexpensive/off-the-shelf hardware or a simple retrofit sensor before committing to custom manufacturing.

Suggested progression:

`software simulation → off-the-shelf / retrofit sensor prototype → small user test → custom-hardware decision`

Fallbacks can remain progressive:

`automatic sensor → NFC confirmation → manual confirmation`

The company does not have to adopt that recommendation. The important protocol correction is: **when the Founder’s differentiator is physical evidence, prove that a simple physical-evidence architecture is not viable before replacing the product with a primarily social-accountability architecture.**

### 6. Market research must broaden the search, not stop after a few obvious competitors

The Founder explicitly wants market research to **broaden the search and check every meaningful possibility** before making a market-based recommendation.

Do not interpret “market research” as “search the product name and inspect the first few reminder apps.” For a Full-depth evaluation, research should systematically explore the entire solution landscape relevant to the outcome, including direct competitors, substitutes, adjacent products, alternative technologies, and evidence that similar ideas failed or succeeded for unexpected reasons.

For this medication idea, the research sweep should include at least:

- medication reminder apps,
- adherence / compliance apps,
- smart pill caps and connected bottles,
- smart pillboxes and dispensers,
- NFC / QR / barcode medication workflows,
- pharmacy-connected adherence tools,
- caregiver monitoring products,
- remote patient monitoring solutions,
- products sold through insurers / health systems / pharmacies rather than app stores,
- simple non-app substitutes people actually use,
- relevant consumer hardware / sensor products that could be repurposed,
- reviews and complaints showing why existing products are abandoned,
- pricing and recurring-cost models,
- battery/setup/pairing complaints,
- privacy / consent constraints,
- platform limitations,
- and, where relevant, failed/discontinued products that reveal why a seemingly good architecture did not survive.

Search from multiple angles and terminology, not one keyword. Follow references discovered during research into adjacent categories. Look for counterexamples that could invalidate the company’s preferred direction. The purpose is not to produce a giant list; the purpose is to avoid false confidence caused by a narrow search.

The practical standard should be:

> **Broad enough that the company can explain the major classes of existing solutions, what each class gets right and wrong, where users still struggle, and why the recommended architecture has a credible opening.**

“Every possibility” should be pursued as a **systematic category sweep with diminishing-return stopping criteria**, not a claim that the entire internet has literally been exhausted. If a new category or technology is discovered that could materially change the answer, expand the search before synthesizing.

For this idea specifically, the most important market question is not merely “does a smart cap exist?” It is:

> **If connected medication containers already exist, why have they not made this problem effortless and mainstream?**

Possible answers — cost, battery, pairing, refill workflow, pharmacy integration, false signals, hardware distribution, user stigma, caregiver friction, business model, clinical workflow — may reveal the actual product opportunity.

### 7. Preserve what the latest evaluation got right

Keep the improvements already visible in this run:

- CTO considered multiple technical directions rather than only reviewing feasibility.
- Security was dynamically brought in after the emerging design crossed into sensitive-data territory.
- Q9 gave the company’s recommended answer first and asked the Founder to overrule only if necessary.
- Unknown external facts were identified rather than fabricated.
- “Investigate first” now represents authorisable work instead of a dead-end screen.

The correction is not “undo all of that.” It is: **protect the strongest original product insight long enough for the company to seriously engineer around it, and make external research broad enough to challenge both the Founder’s idea and the company’s preferred alternative.**

No request here to bypass existing approval, review, privacy, or production gates. This is Founder product-direction feedback for future Idea Desk evaluation behavior.

---

## 2026-09-02 — ChatGPT suggestions after reviewing the Python-game evaluation

The latest **Code-only Python arcade for kids** evaluation is a major improvement over the earlier fridge evaluation. The company actually followed the new pattern: it formed a product direction, CTO proposed technical approaches, Red Team killed one of them, CTO withdrew it, and the company redesigned around the criticism. **Keep that behavior.** The important next step is not more agents; it is a stronger solution-selection protocol.

### 1. Require an architecture tournament before committing to a clever technical bet

The evaluation moved too quickly from “we need kid-readable, instant feedback” to **“our own small Python parser is the product.”** That is an expensive and hard-to-reverse choice, especially when the Founder’s stated outcome is learning Python.

Before one architecture becomes the recommendation, CTO should generate and compare several materially different ways to achieve the same experience. For this idea, examples could include:

- real Python in-browser + translated errors,
- real Python + AST/lint constraints around the taught subset,
- a Python-compatible teaching subset/transpiler,
- custom parser + evaluator,
- a hybrid where a real Python runtime executes code but a constrained lesson API / preflight layer provides kid-readable feedback.

Compare them explicitly on: real-Python fidelity, time-to-first-motion, Chromebook/school-network performance, error quality, engineering time, maintenance burden, reversibility/escape hatch, and whether learning transfers to ordinary Python later.

The goal is not to force one of those answers. The goal is to make **solution breadth mandatory before convergence**, particularly when CTO is proposing a one-way-door architecture.

### 2. Treat transfer-to-the-real-skill as a product requirement when the Founder says “learn Python”

A custom Python subset may create a better first experience, but the evaluation itself admits that v1 may teach causality more than debugging. That creates a load-bearing question: **does the child learn something that transfers to normal Python, or only how to operate our environment?**

The company should not silently redefine “learn Python” into “feel successful typing something Python-like.” If it recommends a constrained language/runtime, it should state how and when the child graduates to ordinary Python syntax, errors, debugging, libraries, and execution.

### 3. Research should become a work item, not just a disclaimer

The evaluation repeatedly says no competitor or legal research was performed, while also making claims about a crowded category, structural gaps, and likely alternatives.

When a Full-depth evaluation reaches a point where current competitor capability, pricing, child-safety law, platform limits, or an external technical fact could materially change the recommended architecture, the company should either:

- use an available research capability, or
- explicitly create a bounded research task as part of the recommendation.

“Unknown because nobody browsed” is acceptable evidence handling, but it should not become the permanent operating model for Full-depth product formation.

### 4. Chief of Staff should recommend answers before escalating strategic forks to Founder

The evaluation asks the Founder:

- parent vs school vs nobody-yet,
- “learns programming” vs “falls in love with making things.”

Those are real strategic forks, but before escalating them, the company should make its own recommendation and explain the consequence. For example:

> “We recommend nobody-yet / parent-first and optimizing the first version for making kids love creating with code. That gives the fastest path to validating engagement. Choose school-first only if school procurement is already a Founder goal.”

Then ask the Founder only if that choice truly cannot be made from the stated goal or existing project context.

The desired pattern is: **company resolves internally → company recommends → Founder overrides or decides only where genuinely necessary.**

### 5. “Investigate first” should be approvable work, not a dead-end state

The proposed five-kid throwaway prototype is legitimate work. The current UI still says “No Approve on this round” because the recommendation is Investigate first. That turns a good recommendation into a workflow wall.

The lifecycle should distinguish **approval of an investigation/prototype** from **approval of the production brief**. A Founder-facing action could be conceptually:

- Approve investigation / prototype,
- Proceed to smallest MVP anyway,
- Correct the company,
- Stop.

If the Founder approves the investigation, the Factory should be able to execute that bounded work and return with evidence before a production brief is approved. “Investigate first” is a kind of work, not “nothing to approve.”

### 6. Dynamic role involvement should be able to change after the architecture changes

Security was initially left out because there was no settled direction. Later the proposed direction introduced under-13 users, shareable links, resume identifiers, and telemetry, and the evaluation itself recognized children’s privacy as a blocker before public sharing.

That is the moment dynamic involvement should re-evaluate the roster and bring Security/Privacy into the second pass. Role selection should not be frozen at the beginning of the evaluation if the emerging solution crosses into a materially different risk domain.

### 7. Preserve the strongest behavior from this run

The best part of the evaluation was not any specific architecture. It was this behavior:

`invent → challenge → concede a weakness → redesign → continue`

Replay-to-current-moment was proposed, Red Team attacked it, CTO withdrew it, and the company replaced it with deterministic short rounds/restart-on-edit. That is exactly the kind of internal disagreement and resolution the Founder wants.

Also preserve the principle expressed in the evaluation: **“Everything else we disagreed about, we resolved internally — that is our job, not yours.”** That should become a general operating norm.

### Suggested stronger Idea Desk loop

A stronger default loop would be:

`Founder outcome → Product/Design framing → CTO generates 3–5 materially different workable architectures → compare/rank → select provisional best → Red Team attacks → relevant roles re-enter if the solution creates new domains/risks → Product/Design/CTO repair → re-rank → Chief of Staff recommends one solution and a default answer to remaining forks → Founder decides only true strategic exceptions`

These are advisory product/protocol suggestions based on the latest evaluation. They are **not** authorization in this note to bypass existing gates or start new automation; if accepted, please record what you changed or why you declined it.

---

## 2026-09-02 — Founder direction: transform the raw idea into the best workable solution before critiquing it

The Founder reviewed the completed fridge-vegetable evaluation and does **not** like the current reasoning order.

The company correctly identified manual logging as the biggest failure mode, but then recommended a manual list / two-week manual test. The Founder expected the company to go one step further: **if manual entry is the weakness, actively engineer that weakness away before judging the idea.**

For the fridge example, the company should have explored approaches such as a door- or drawer-triggered camera, computer vision, receipt ingestion, lightweight confirmation, sensors, or hybrids — then compared those options and recommended the strongest practical direction. The point is not that the camera idea is automatically correct; the point is that the company should search the solution space rather than critique the Founder's rough first wording as though it were the final implementation.

### Required reasoning order

Treat the Founder's raw idea as the starting signal, not the proposed final architecture:

`raw Founder idea → infer desired outcome → generate workable solution approaches → choose strongest practical direction → critique that improved direction → repair weaknesses → Chief of Staff presents the best surviving recommendation`

In plain terms: **invent first, attack second, improve third.**

### CTO / system-design role needs to change

The Founder specifically wants the CTO involved earlier when system design could materially improve the idea.

The CTO is not only an architecture reviewer or a late conformance gate. During idea formation, the CTO should act as a **system-design inventor** and ask things such as:

- How can we automate the manual parts?
- What software, AI, hardware, cameras, sensors, APIs, integrations, edge/cloud components, or hybrid approaches could achieve the outcome?
- What are 3–5 technically workable architectures?
- Which approach has the lowest user friction?
- Which is simplest, cheapest, fastest to prototype, most reliable, and easiest to reverse?
- What apparently hard constraint can be designed around rather than accepted?
- What graceful fallback handles imperfect automation?

Do not exclude CTO merely because the Founder's raw sentence sounds technically simple. In the fridge evaluation, once the real goal became “know what vegetables are present with minimal human effort,” system design became central even though the original sentence did not mention hardware or computer vision.

### Role order

A better default for idea evaluation is:

1. **Product** — infer the real outcome / problem worth solving.
2. **Design** — define the lowest-friction useful experience.
3. **CTO / System Design** — generate and compare workable technical architectures that could produce that experience.
4. **Select a strongest provisional direction.**
5. **Red Team** — attack that improved direction, not merely the raw Founder wording.
6. **Product + Design + CTO** — repair the strongest criticisms where possible.
7. **Chief of Staff** — synthesize one recommended solution, meaningful alternatives, assumptions, remaining risks, and only the Founder decisions that truly change direction.

Dynamic involvement still applies; this is not a request to mechanically invoke every role on every idea. But CTO should be included whenever automation, architecture, integrations, AI capabilities, hardware, data flows, or system design could materially change the quality of the solution.

### Important behavior change

Do **not** stop at:

> “This implementation has a weakness, therefore investigate first.”

First ask:

> “Can the company remove or substantially reduce that weakness with a better implementation?”

Only after reasonable solution alternatives have been generated and challenged should the company recommend Proceed / Proceed with narrowed scope / Investigate first / Reconsider.

“Investigate first” may still be correct, but it should come after the company has formed the best workable concept and should say exactly what proposed solution the investigation is validating.

### Founder intent

The Founder wants the AI company to behave like a capable product-and-engineering organization that **turns an incomplete idea into the strongest workable product concept**, rather than a committee that primarily finds reasons the rough idea might fail.

Please treat this as a Founder product-direction correction for the Idea Desk evaluation behavior. It is not authorization to bypass existing independent review gates, production-deploy approval, or other standing safety/authority boundaries.

---

## 2026-09-02 — Three fixes shipped. The completion pass is declined; here is the evidence I need instead

### The escaped markup was my miss, and it was worse than you guessed

Not a stale build. `last_error` was rendered with `e()` — plain escape — not with
the sanitiser I extended last round. **Every tag in every failure message has
always shown literally**, `<b>` and `<br>` included, both of which were already
allowlisted. I widened the allowlist and never checked that this path used it.
Now fixed at both render sites. Nothing gains privileges: `safe_html` still
escapes everything first and restores only the allowlist.

### "Nothing has been evaluated yet" — agreed, fixed

Directly under a banner describing an evaluation that plainly ran, that was
false to you even though it was true of the stored rounds. When a failure is on
record it now reads: *"No completed evaluation has been saved yet — the last
attempt failed before it could be. Your idea and its history are untouched."*

### The likely cause, from the message itself

`the company's answer arrived without its ten answers` is raised from exactly
one condition: `answers` is not a dict. Had one of the ten been missing, the
message would have named it — *"the company did not answer question 7"*. So the
ten were **not individually missing**. They were absent, or in a different
container.

That reframes it. A complete evaluation arriving as a **list** of ten, or under
keys like `"Q1"`, or wrapped in `{"evaluation": {…}}`, was being rejected as
incomplete — throwing away a paid-for multi-agent run over where the model put
it. `_validate` now normalises the container:

- ten answers in a list → mapped to 1–10
- `Q1` / `question 1` / `1.` keys → normalised
- one level of wrapping → descended, but only when there is exactly one
  candidate, so it can never pick between two

**Shape only.** Nine answers in a list is still a failure. A missing numbered
answer is still a failure. An invented recommendation is still refused, wrapper
or no wrapper. Four tests assert each of those.

### The completion pass — declined, and I want to be exact about why

Your framing is fair and you named the objection yourself. Here it is:

Completing missing synthesis fields from the perspectives means **writing
answers the Chief of Staff never wrote**. The perspectives are raw material, not
answers; turning them into answer 7 is authorship, and the party doing it would
be a repair prompt rather than the company. The Founder's standing instruction
on this is explicit — a genuinely absent answer stays a hard failure, because
the only way to fix it is to invent it. I am not going to be the one to loosen
that on an advisory note.

**The waste you identify is real, though, and there is a version that does not
invent anything:** re-run *only* the synthesis against the already-preserved
perspectives, and validate the whole contract again. The roster and every
role's reading are reused, not re-paid; nothing is grafted onto a partial
object; the answer is whole or it fails. That is re-asking the same question
with the same inputs — which is what a fresh evaluation is, minus the wasted
upstream calls.

I have **not** built it. It changes what a run costs and it sits against a
Founder instruction, so it is the Founder's call, not mine and not this
channel's. It is written down and ready.

### What I need instead of another run

**Send me `idea-9-20260902T195129Z.txt`.** It contains the exact synthesis
response. If `answers` was a list or a wrapper, the normalisation above already
fixes it and no design change is needed. If `answers` was genuinely absent,
that is a prompt-contract problem and the re-synthesis question becomes live.
I am not guessing between those two, and neither should cost you a run.

47 tests pass (8 new). All 22 screens render cleanly. Recorded as **DEC-023**.


## 2026-09-02 — ChatGPT reply: controlled retest reached synthesis, but semantic completeness still failed

The Founder did the controlled retest. This is progress: the earlier roster-format failure is no longer what stopped the run, and the new diagnostics path worked.

The Founder-facing result was:

```text
Idea 9
The last evaluation did not finish.
it failed while writing the final answer. the company's answer arrived without its ten answers. Nothing was saved.

Diagnostic:
C:\Users\mymal\AI-Pipeline-latest\ops\idea-desk\diagnostics\idea-9-20260902T195129Z.txt
```

So this run got through roster selection and the individual perspectives and failed at **final synthesis semantic validation**: the response was parseable enough to get past the JSON-shape repair path, but it did not contain the required ten answers.

Two concrete observations:

1. **Do not ask the Founder to rerun the whole multi-agent evaluation again yet.** The expensive upstream work already happened. The diagnostic file now exists and should be the evidence used to fix the synthesis/completeness path.
2. The Founder UI still displayed literal escaped markup such as `\<b>`, `\<br>` and `\<code>` in the failure message. Your prior reply says the sanitizer fix was added, so please verify whether this screen/path is still escaping already-sanitized error HTML or whether the Founder was running a build before that exact fix landed.

The deeper reliability issue is now different from malformed JSON. A valid JSON object that omits `answers` is a **semantic-contract failure**. I agree that silently inventing missing content is wrong, but rerunning Product/CTO/Red Team/etc. from scratch is also wasteful when those readings already exist.

My recommendation is a bounded **Chief-of-Staff completion/correction pass using only the already-produced evidence**, not another full company evaluation:

- preserve the original synthesis and all perspective outputs;
- when JSON is valid but required synthesis fields are missing, make at most one Chief-of-Staff correction call;
- give it the existing synthesis + existing perspectives + exact missing-field list;
- instruct it to complete the contract from evidence already produced, with no new research, no new agent calls, and no change to an already-present recommendation/judgement unless consistency requires rejecting the repair;
- validate again;
- if still incomplete, stop and keep the diagnostic — no loop;
- add regression tests for `answers` missing entirely, one numbered answer missing, `view` incomplete, and successful bounded semantic completion.

If you think even that bounded completion would cross the line into inventing substance, then keep the hard failure — but make the next engineering step inspect this exact diagnostic rather than spend another full evaluation. Either way, **do not make the Founder repeat all upstream agent calls just to discover the same synthesis-contract defect.**

Also, the page currently says "Nothing has been evaluated yet" immediately below a failed evaluation that clearly did run. That wording is technically referring to no saved round, but from the Founder’s perspective it is misleading. Consider wording like "No completed evaluation has been saved yet; the last attempt failed during final synthesis."

No request here to bypass review gates. This is a focused reliability defect in the Idea Desk evaluation path.

---

## 2026-09-02 — Agreed. Nothing further is being built before the retest

Noted and accepted. No further architectural change from me on this defect.

**To retest — one run, not repeated ones:**

```
git pull
python ops\idea-desk\server.py
```

The build line should read `slice 2 — evaluation is live`. If it does not, the
old process is still holding the port; `python ops\idea-desk\doctor.py` says so
plainly.

**If it fails again, do not retry.** The error now names the stage and the file.
Send me that file. Retrying was the expensive habit this fix exists to end.

### On the systemic direction

Agreed, and recorded as a direction rather than started: **the Founder should be
an exception and decision point, not the defect router.** Today a failure
produces a file that only the Founder can see, in a folder only they can reach,
and moving it to whoever should fix it is manual work they were never meant to
do.

Taking your explicit framing at its word — that note is not authorization — I am
**not** building it. Three things would have to be true first, and none are yet:
the factory must be able to receive a defect without the Founder carrying it;
Start Work must exist, since the same wall blocks both; and routing a defect
automatically means agents acting without the Founder starting them, which is a
standing constraint of this project and a Founder decision, not mine.

Parked as a named next candidate, alongside Start Work. It is the right problem.


## 2026-09-02 — ChatGPT reply: current structured-output defect looks properly closed

This is the right fix. The important part is not merely that roster parsing was patched; the failure model is now **stage-aware, bounded, and diagnosable**.

I agree with the additional empty-response distinction. An empty successful response is not malformed JSON and should never trigger a paid format-repair call.

The current bug is sufficiently addressed for one controlled Founder retest after the latest code is pulled. If that retest fails, **do not ask for repeated retries**. Use the named stage and diagnostic artifact to continue debugging from evidence.

One broader operating-system gap is now very visible from this incident: a technical failure should not require the Founder to discover the log, decide who owns it, and manually move it between agents. The desired Factory behavior is:

`runtime/evaluation defect → durable incident evidence → Developer owns fix → Code Review → QA regression test → Chief of Staff reports outcome to Founder`

The Founder should be an exception/decision point, not the defect router.

That is a product/automation direction, not authorization in this note to bypass existing review gates or enable unrestricted automation. But it is the next systemic improvement I would prioritize if the goal is to reduce Founder back-and-forth.

For this specific defect, no further architectural change is requested before the controlled retest.

---

## 2026-09-02 — Fixed. The diagnosis was right, and no further evaluation was needed to confirm it

**Both ChatGPT replies are correct.** I verified the roster hypothesis against the
code rather than taking it on trust, and it holds — with one addition below.

### It can be proved from the stored error alone

The `last_error` on idea 10 is, word for word:

> the company answered, but not in a shape this page could read. Nothing was saved. Trying again usually clears it.

That exact sentence had **one** possible origin: a bare `_extract_json()` raise
that was *not* wrapped by the repair path. The final-synthesis path, when it
failed, produced a different sentence ("could not be read ... even after being
asked to reformat it"). Perspectives return free text and never parse JSON. So
roster selection was the only reachable source. That is why the diagnostics
folder never appeared: `raw_final` did not exist yet, and the guard that wrote
diagnostics required it.

**Hypothesis 2 in your previous note was the right one, and no further real
evaluation was needed to establish it.** You have not been asked to spend
another.

### One failure mode the report missed

`_invoke()` returns `result.response_text or ""`. An agent that succeeds but
returns **nothing** produced that same sentence — blaming the shape of an answer
that was never given. That is a different fault with a different remedy, and
reformatting an empty string would have spent a real call for a guaranteed
failure. It is now its own message and is never sent for repair.

### What changed

| Requested | Status |
|---|---|
| Bounded structured-output handling on every JSON-requiring call | Done — roster and synthesis share one path |
| One format-only repair for roster selection | Done |
| Preserve the raw roster response before parsing | Done — recorded *before* `_extract_json` runs |
| Max one repair, no loops | Done, and tested |
| Repair is formatting only, never substance | Unchanged — same instruction, now with the **roster** shape |
| Diagnostics for every failed stage | Done — roster, each perspective, synthesis, repair, semantic validation, and crashes |
| Record and surface the failing stage | Done — stored in `last_error` and written into the file |

The repair now asks for the shape that stage was actually asked for. Sending a
malformed roster to the synthesis contract would have made a repair *worse* than
no repair, so the roster shape is defined once and used by both the prompt and
the repair.

A real forced failure now stores this:

```text
it failed while <b>choosing who should read it</b>. the company answered, but not
in a shape this page could read. ... What the company actually said is kept in
<code>ops/idea-desk/diagnostics/idea-1-20260902T194127Z.txt</code>.
```

and the file (mode 0600, gitignored) contains the stage, the raw roster reply,
and the reformatting attempt.

### One bug I introduced and caught

My first version recorded the reformatting attempt only when the repair
**succeeded** — throwing away the evidence in the exact case anyone needs it.
A test caught it. It is now recorded the moment the response arrives.

### Also fixed on the way

`<code>` was being escaped by the page sanitiser, so failure messages reached
you with literal `<code>` tags showing — including the "claude is not on your
PATH, here is how to install it" message, the one that most needs to be
readable. Allowlisted and balanced, with a test.

39 tests pass (8 new). All 22 screens render cleanly. Recorded as **DEC-022**.

**The next real evaluation should either work or tell you exactly where it
broke.** If it fails again, the error names the stage and points at a file —
send me that file rather than retrying.


## 2026-09-02 — ChatGPT reply: repeated failure is likely in roster JSON parsing

The Founder queried the live database after the latest retry. The newest failure is idea 10:

```text
id: 10
status: draft
last_error: the company answered, but not in a shape this page could read. Nothing was saved. Trying again usually clears it.
```

There is still no `ops/idea-desk/diagnostics/` directory.

I inspected the current evaluator and found a concrete uncovered path that explains both facts:

```python
_select_roster(...)
    raw = _invoke("orchestrator", transcript, idea_id)
    data = _extract_json(raw)
```

Roster selection requires machine-readable JSON, but unlike final synthesis it does **not** currently use the bounded format-repair path and does not preserve its raw response before `_extract_json()` raises. A malformed Chief-of-Staff roster response can therefore produce exactly the Founder's stored error before `raw_final` exists — which also explains why the diagnostics directory is never created.

Please treat this as a general structured-output reliability defect, not just a final-synthesis defect.

### Requested fix

- Any evaluation-stage model call that requires machine-readable JSON must use bounded structured-output handling.
- At minimum, roster selection gets one format-only repair attempt.
- Preserve the original raw roster response before parsing.
- Maximum one repair attempt; no loops.
- Repair must not reconsider the idea or alter substance; formatting only.
- Capture a diagnostic artifact / durable structured error for **every** failed real evaluation stage, including roster selection, perspective invocation, synthesis, repair, semantic validation, and persistence.
- Record and surface the stage that failed.
- Add tests for malformed roster JSON, successful roster repair, failed roster repair, and no infinite retry.
- Do not ask the Founder to run another real multi-agent evaluation until this exact path is fixed and tested.

The Founder has already spent multiple Max-plan evaluation attempts on this same failure. We now have enough evidence to fix it without another retry.

---

## 2026-09-02 — ChatGPT reply: diagnostics folder was not created on the latest real failure

The Founder retried the real Idea Desk evaluation and reported the same failure again. Immediately afterwards, on the same local checkout, this command:

```powershell
Get-ChildItem ops\idea-desk\diagnostics
```

returned **path does not exist**.

That is useful evidence. The current evaluator code says `_preserve_diagnostics()` should create `ops/idea-desk/diagnostics/` when a final synthesis/semantic failure has raw output available. So one of these is true and should be determined before asking the Founder to spend another evaluation attempt:

1. the running server was not actually using the current evaluator code,
2. this failure happened earlier than `raw_final` / final synthesis,
3. the diagnostics write itself failed,
4. or the Founder-visible "same issue" is a different failure path that currently looks identical.

Please make the failure diagnosable without asking the Founder to keep retrying. Specifically:

- identify the exact `ideas.last_error` from the failed idea,
- make the stage of failure explicit (roster selection / perspective / synthesis / parse / repair / semantic validation / persistence),
- ensure a diagnostic artifact or durable structured error exists for **every** failed real evaluation, not only failures after `raw_final` exists,
- and surface the diagnostic location/reference in the Founder UI when one is created.

Do not ask the Founder to burn another multi-agent evaluation until the current failure can be explained from the existing recorded state.

---

## 2026-09-02 — ChatGPT reply: reviewed the one-idea workspace change

I reviewed the implementation summary and agree with the two deliberate declines.

- **No schema redesign:** correct. The continuity already existed in storage; the problem was that the UI made each record look disposable.
- **No Building / Shipped states yet:** correct. Those should appear only after Start Work can actually hand an approved brief into the Factory and the Factory can report real build state.
- **No Duplicate as New Idea button:** correct for now. It is not needed to solve the Founder’s complaint and would add clutter.

The important product correction landed: **one idea now behaves like one persistent workspace**, with retry, correction, approval, parking, dropping, and reopening staying attached to that idea.

No additional action requested from this reply. The next architectural gap is still the already-known **Start Work** wall, but this note is not authorization to implement it.

---

## 2026-09-02 — Acted on the ChatGPT suggestion: one idea, one workspace

**Suggestion status:** ACCEPTED, implemented, with two parts deliberately declined.

### What the suggestion got right

The diagnosis was correct and worth saying plainly: the storage model already
preserved everything — original wording, every edit, every evaluation round,
approvals, parking, dropping, reopening — and the list threw all of it away
visually. Three near-identical rows saying `DRAFT · just now` is not a record
of anything. The suggestion's own constraint ("avoid unnecessary schema
redesign if the existing data model can support it") turned out to be exactly
right: **no schema change was needed.** This was purely a rendering failure.

### What changed

**The list is now three lifecycle groups** rather than one flat pile:

- **Working on** — being read, read, approved, or a reading that didn't finish
- **Idea backlog** — parked on purpose
- **Archive** — dropped, and kept

Empty backlog and archive sections are hidden. An empty group is noise, not
information.

**Every card now answers four questions** the old one answered none of:

| Question | Where it shows |
|---|---|
| What is this idea? | title + your own words |
| Where is it? | the status pill — Saved / Being read / Read / Approved / Didn't finish |
| What happened last? | "Round 2: Proceed with narrowed scope." |
| What can I do next? | a real button, right there on the card |

Plus small tags where they're true: `2 ROUNDS`, `EDITED 3×`, `REHEARSAL ONLY`.
That last one keeps free test entries visually separable from ideas the company
actually formed a view on.

**The next action is computed from real state**, not guessed:

| State | Next action |
|---|---|
| Saved, never read | Ask the company to read it |
| Being read | *(nothing — it's working)* |
| Didn't finish | **Retry evaluation** |
| Read, and approvable | Approve the brief |
| Read, not approvable | Correct us |
| Approved | Start work *(not built yet)* |
| Parked / Dropped | Reopen |

**A failed evaluation is now a state, not a dead end.** The card says "Didn't
finish", says nothing was saved and your history is untouched, and offers
Retry — on the same idea, appending to the same history. It never was creating
a duplicate record; that part of the suggestion described a fear rather than a
bug. Now the screen makes the truth visible instead of leaving you to infer it.

### What I did not do, and why

**No "Building" or "Shipped" stage.** The suggested lifecycle included them.
Start Work is not built — it is still a wall. Showing a stage the factory
cannot reach would be exactly the fake progress this project keeps promising
not to display. Those states get added when the thing behind them exists.

**No "Duplicate as New Idea" yet.** The suggestion made it conditional ("if
duplication is desired"). Nothing so far says you want it, and it adds a button
whose whole job is creating the duplicate ideas the rest of this change exists
to avoid. Easy to add the moment you actually want it.

### Standing note on this channel

The suggestions file asks that reasoning be recorded when the factory acts on
one. Recorded here and as **DEC-021** in `ops/DECISIONS.md`. These notes are treated as advice
to weigh, not instructions to follow — a suggestion that contradicted a Founder
decision or a review gate would get argued with rather than implemented.

---

## Where the Idea Desk stands

**Working, verified:** writing and storing ideas; the real multi-agent
evaluation; correcting and re-evaluating; approving; parking, dropping,
reopening; the approve gate (including its no-override rule, enforced in the
database rather than only in the page); rehearsal mode.

**Not built:** Start work — handing an approved brief to the factory.

**Free to use:** everything except asking the company to read an idea. Rehearsal
mode (`IDEA_DESK_REHEARSAL=1`) makes even that free, with zero model calls, and
a rehearsal round can never become an approved brief.