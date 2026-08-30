# Red Team review — Phase 2, Milestone 2B4 architecture

TASK-013. Reviewing `ops/reviews/cto-milestone2b4-architecture.md` (§13
incorporating Security's C1–C3 fixes) and
`ops/reviews/security-milestone2b4-threat-model.md` before Development
builds anything. Not re-doing Security's 24-item threat disposition or
independent verification (DB write path, `.gitignore` pattern, session
fixation, scrypt parameters, §11's central claim) — accepted as sound.
This review applies Red Team's own lens: overengineering, simpler
alternatives, hidden dependencies, architecture conflicts, an
under-weighted security angle Security's own scope didn't cover, hidden
implementation cost, tech debt, beginner mistakes, and unsupported
assumptions. Findings below were independently tested, not just read —
concurrency/GIL behavior of `hashlib.scrypt`, the `maxmem` `ValueError`,
empty-passphrase behavior, and a factual claim about existing code were
all verified directly against this machine and this repository, not
taken on either document's word.

## Verdict: PASS with conditions

Design direction is sound and correctly scoped, matches this project's
"smallest appropriate mechanism" convention, and the C1–C3 fixes close
the two exploitable gaps Security found. Nothing here requires
re-architecture, touches `risks.id=3`, or reopens Security's own
findings. One real, previously-undisclosed availability gap found below
(not identified by either prior document) must be added to the design's
own disclosure sections before Development starts — cheap to fix (text
only, no code/architecture change) and consistent with this project's
existing practice of disclosing every known limitation rather than
leaving it inferred. One factual citation in §10 is wrong and must be
corrected. Two minor implementation-robustness notes for Development.
None of this rises to REJECT.

## Required before Development starts (conditions, not a full reopen)

**F1 — Shared, non-identity-scoped lockout enables a sustained
denial-of-service against the Founder's own login, not just a brute-force
defense — undisclosed in either document.** §8 (correctly) uses one
global lockout counter, not per-identity, because there is exactly one
Founder/credential — Security concurred this is right, and it is. But
this has a consequence neither document states: because the counter and
`_locked_until` are *shared* across every caller, and because C1 requires
`/api/login` requests to be fully serialized through `_LOGIN_LOCK`, an
attacker already inside this design's own assumed "another local
process/page reaches the Control Center" threat class (Founder threat
item 1 — the same class §7 already treats as able to read `/login`'s
unauthenticated page and its embedded CSRF token, satisfying C2 trivially)
can sustain a flood of failed `/api/login` POSTs indefinitely. Traced
through concretely: each 30s lockout cycle allows exactly 5 real `scrypt`
verifications (~5s) before `_locked_until` is set again; if the attacker's
flood reliably wins the race to consume those 5 slots in each cycle
(trivial for a process sending many requests per second against a Founder
who submits one browser form occasionally), the Founder's own genuine
login attempts land in the "currently locked, 429" branch far more often
than not, for as long as the flood keeps running — a real, if not
absolute, denial of the Founder's own access to their tool, caused by the
brute-force defense mechanism itself.

Independently verified this isn't secretly worse than believed:
`hashlib.scrypt` **does** release the GIL during computation (measured
directly — a concurrent busy-loop thread completed ~90% of its
uncontended throughput while a `N=2**17` `scrypt` call ran on another
thread), so C1's full-critical-section lock only serializes `/api/login`
against itself — it does **not** freeze every other route on the server
while a login's `scrypt` call runs. That would have been a much worse,
blocking-severity finding; it is not what happens.

This does not require a code fix — no cheap in-scope mechanism closes it
without weakening something else (per-source-IP limiting is theater, as
§8 already says, since every local caller shares `127.0.0.1`; anything
better requires distinguishing "the real Founder" from "a co-resident
process," which is exactly `risks.id=3`'s territory, out of scope). The
Founder's actual remedy is the same one this design already relies on
elsewhere (§8's own "by the time someone can restart this process they
already have a level of local access that makes X the least of what it
grants them" reasoning, and §11's general framing): identify and stop the
flooding process, which they can always do as the owning OS user.

**Required**: add explicit disclosure of this residual limitation to §8
(and the eventual `SECURITY.md` section), in the same disclosure style
already used for every other known gap in this design (§11's Bash-agent
gap, the unbounded-follow-up-rounds gap carried over from 2B3B). This is
a documentation requirement, not an architecture change, and should not
block a re-review from passing once added.

**F2 — §10's supporting citation is factually wrong; fix before this
ships as written.** §10 justifies the new `threading.Lock` usage by
citing "the same category of primitive `agent_runtime.py` already uses
for its process-group registry (2B3A's shutdown-cleanup mechanism), not a
new pattern." Verified directly against the shipped code: `agent_runtime.py`
contains **no** `threading.Lock` and **no** process-group registry —
that registry was *proposed* in the 2B3A architecture draft and
explicitly **rejected** by Red Team's own 2B3A review
(`ops/reviews/red-team-milestone2b3a-architecture.md`, finding 5: "REJECT
as proposed... recommend dropping it"), then dropped. What
`agent_runtime.py` actually uses is `threading.BoundedSemaphore`
(`_INVOCATION_SEMAPHORE`, line 174) guarding `MAX_CONCURRENT_INVOCATIONS`
— a related but different primitive, and real precedent on its own terms
(this codebase already uses `threading` module primitives to guard shared
mutable state under `ThreadingHTTPServer`, which is the actual point §10
is making). The underlying architectural claim — "not a new competing
concurrency system" — still holds once corrected; only the citation is
wrong. **Required**: correct §10 to cite `_INVOCATION_SEMAPHORE`/
`threading.BoundedSemaphore`, not the rejected registry, before this
document is treated as final. This is exactly the kind of unverified
claim this project's own review convention (2B3A's Red Team review: "not
assumed... verified by reading `do_POST()`'s single dispatch block") says
should be checked, not repeated.

## Non-blocking recommendations for Development

- **Partially-written credential file on hot-reload.** §3's "no restart
  required" hot-reload path (checking `Path.exists()` on every request)
  is real and correct, but neither document states what happens if a
  request's credential-file read/parse lands in the narrow window between
  `founder_auth.py setup`'s `os.open(..., O_EXCL, 0o600)` call and the
  JSON content finishing its write — a concurrent `json.load()` on a
  truncated/partial file would raise `json.JSONDecodeError`, and nothing
  says this is caught. Extremely narrow window, first-run-only, and not a
  security issue (no information disclosure), but Development should wrap
  the read/parse in a try/except and treat a malformed file the same as
  "setup required" (503) rather than let it surface as an unhandled 500.
- **§9's optional mtime-tamper-detection baseline should anchor at server
  startup, not only at "last check."** As worded, if the credential file
  is modified before the *first* login-check-triggering request ever
  arrives, there's no prior cached mtime to compare against. Cheap fix if
  Development builds this optional feature at all (open question 4):
  cache the mtime once at server startup in addition to refreshing it on
  each check.
- Confirmed independently, no objection: `hashlib.scrypt` with the
  default `maxmem` does raise `ValueError` on `N=2**17, r=8`, and the
  explicit `maxmem=132*1024*1024` fixes it (reproduced); `hashlib.scrypt(b"", ...)`
  does not raise (reproduced) — both claims in §2/§13-C3 are accurate as
  stated, not just asserted.

## Answers to the nine review lenses

1. **Overengineering**: No. `scrypt` parameters match OWASP's current
   general-purpose guidance and cost ~1s on a rarely-hit path; the session
   mechanism (cookie + in-memory dict + two timeouts) is the minimum
   needed for a stateful "am I still unlocked" check and is simpler than
   the realistic alternative (HTTP Basic Auth would force either
   re-running `scrypt` on every single request or building an equivalent
   cache — i.e., reinventing this same session mechanism — while also
   losing a clean logout affordance). The two `founder_auth.py`
   subcommands and the credential JSON's version/KDF-parameter fields are
   proportionate, not speculative. Nothing here is more elaborate than
   the threat model justifies.
2. **Simpler alternative**: None found that closes `risks.id=2` to the
   same degree without touching `risks.id=3` or adding a dependency.
   Concur with §1's rejection of WebAuthn/OS-keychain/TOTP for this
   threat model.
3. **Hidden dependencies**: None. Confirmed `server.py`'s current imports
   are stdlib-only end to end (`re`, `secrets`, `sqlite3`, `sys`,
   `http.server`, `pathlib`, `urllib.parse`, plus this project's own
   modules) — the proposed additions (`hashlib`, `getpass`, `argparse`,
   `json`, `os`, `threading`, `time`) are all stdlib. No third-party
   package anywhere in the design.
4. **Breaks architecture**: No. `opsdb.py` remains the sole DB writer —
   independently confirmed no `opsdb.*` call exists anywhere in the
   credential/session design, consistent with Security's own check.
   `agent_runtime.py` remains the sole model-invocation boundary — this
   feature never invokes a model. The `do_POST()`-centralized-check
   pattern is extended, not bypassed. §10's *concurrency* claim is
   correct in substance (see F2 for the citation error) —
   `ThreadingHTTPServer`'s worker-thread-per-connection model is
   unchanged, and the new locks guard only brief in-memory
   read-modify-write sections, never a model invocation or a DB write.
5. **Security/privacy (under-weighted angle)**: F1 above — the shared
   lockout's self-DoS potential against the Founder's own access,
   introduced in effect by C1's correct-but-consequential full
   serialization, and not identified by either prior document.
6. **Hidden costs**: §12's files-touched list is realistic; grepped this
   repo for any operational doc instructing "how to start `server.py`"
   that would also need updating and found none, so the list isn't
   missing an obvious doc-touch. `founder_auth.py` as a separate CLI
   matches this codebase's existing convention (`opsdb.py`) rather than
   adding a new one; `argparse` provides `-h`/`--help` for free, so "the
   Founder forgets the invocation" is a smaller risk than the prompt
   suggested — not a real gap.
7. **Tech debt**: In-memory-only `SESSIONS` forcing re-auth on every
   restart is deliberate and justified (§4), and Security's own
   idle-timeout/form-data-loss UX flag already covers the realistic
   pressure-toward-a-workaround concern; concur it's non-blocking, not
   ignored.
8. **Beginner mistakes**: None found. Verification compares derived hash
   bytes via `secrets.compare_digest`, never raw passphrases; audit
   logging explicitly excludes passphrase/hash/salt/session id/token;
   the `dbutil.write_output()` TOCTOU gap was correctly identified and
   avoided (`O_EXCL`/`os.replace`), confirmed by reading `dbutil.py`
   directly (`path.write_text()` then `path.chmod()` — a real gap for
   that helper, correctly not reused here); no off-by-one in
   `MAX_FAILED_ATTEMPTS` (all 5 attempts are genuinely verified before
   lockout triggers, matching §8's own stated cost math).
9. **Unsupported assumptions**: The 30-minute idle / 12-hour absolute
   session lifetime is not contradicted by anything in this repo, but
   also isn't supported by any real usage data — `meetings`/`messages`
   tables are currently empty in this environment, and
   `EXECUTIVE_MEETINGS.md` documents the feature's shape, not real
   session durations. The CTO doc already flags this honestly as its own
   open question 2; concur it should be validated empirically once real
   usage exists rather than tuned further now.

## Summary of conditions Development/CTO must close before build

1. Add explicit disclosure of the shared-lockout self-DoS residual risk
   (F1) to §8 and the eventual `SECURITY.md` section — text only.
2. Correct §10's citation from the rejected 2B3A process-group registry
   to the actually-shipped `_INVOCATION_SEMAPHORE`/`BoundedSemaphore`
   precedent (F2) — text only.
3. (Non-blocking) Development should handle a malformed/partial
   credential-file read gracefully (503, not an unhandled 500).
4. (Non-blocking) If §9's optional mtime tamper-detection ships, anchor
   the baseline mtime at server startup, not only at first check.

None of the above require a new mechanism, touch `risks.id=3`, or reopen
Security's C1–C3. Re-review not required once items 1–2 land in the
document; Development may proceed against the corrected document.
