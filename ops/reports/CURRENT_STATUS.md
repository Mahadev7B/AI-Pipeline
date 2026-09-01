# CURRENT_STATUS.md

Generated 2026-09-01 23:47 UTC by `ops/db/report.py` from the live database — do not hand-edit; re-run the script instead.

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
- TASK-016 — Risk id=3 architecture investigation: can agent access be scoped below the Bash tool-category level
- TASK-018 — Product architecture completion review: remaining Phase 3, Founder Work Progress capability, Founder Test Readiness definition, ROADMAP correction
- TASK-019 — Milestone A: Active Work dashboard + Task Detail page
- TASK-020 — Milestone B: Company-wide AI cost visibility
- TASK-021 — Milestone C: Company-wide Risks register
- TASK-022 — Milestone D: Project / Phase Progress

## In progress
- TASK-023 — risks.id=3 durable closure: OS-level/process-separation sandboxing for Developer (ARCHITECTURE, owner: cto, progress: not broken into steps)
- TASK-024 — Founder Idea Intake: submit a new idea from the Control Center UI (MOCKUP_REVIEW, owner: design, progress: not broken into steps)
- TASK-026 — Control Center redesign: a flow-first dashboard, not thirteen tabs of text (MOCKUP, owner: —, progress: not broken into steps)

## Blocked
- TASK-017 — Risk id=3 reduction milestone: reviewer zero-tool rollout + self-immune Developer denylist: no reason recorded

## Waiting (Backlog)
- TASK-025 — Divergent-thinking stage: real brainstorming before requirements lock, and working agent skills

## QA failures (unresolved)
- TASK-017 — Live, real-invocation test of the self-immune Developer PreToolUse denylist hook (fail-closed contract), plus full synchronous reviewer-route testing, in an isolated scratch clone/DB/credential/server (never live repo/DB).: CRITICAL: the shipped Developer denylist hook never runs at all under a real, reachable, non-adversarial condition, silently fail-OPEN, contradicting the exact property 3 review rounds were spent hardening. Live evidence: ran 'claude --agent developer --allowedTools Write -p ...' (a real, non-interactive session, in an isolated scratch clone of this repo -- distinct from Task-tool-delegated interactive usage) attempting Write('ops/db/operations.sqlite3','x'), one of the two PRIMARY named-protected paths. It SUCCEEDED -- permission_denials was empty, hook_denials table stayed empty, and the file was genuinely overwritten (verified: 'x', 1 byte, git diff confirmed on the scratch clone only). --debug hooks showed why: '[ERROR] Skipping frontmatter hooks for main-thread agent developer: the folder its definition file came from is not trusted (source: projectSettings)' -- Claude Code's workspace-trust dialog is skipped entirely in non-interactive/-p mode (confirmed in Usage: claude [options] [command] [prompt]

Claude Code - starts an interactive session by default, use -p/--print for
non-interactive output

Arguments:
  prompt                                Your prompt

Options:
  --add-dir <directories...>            Additional directories to allow tool
                                        access to
  --agent <agent>                       Agent for the current session. Overrides
                                        the 'agent' setting.
  --agents <json>                       JSON object defining custom agents (e.g.
                                        '{"reviewer": {"description": "Reviews
                                        code", "prompt": "You are a code
                                        reviewer"}}')
  --allow-dangerously-skip-permissions  Enable bypassing all permission checks
                                        as an option, without it being enabled
                                        by default. Recommended only for
                                        sandboxes with no internet access.
  --allowedTools, --allowed-tools <tools...>
      Comma or space-separated list of tool names to allow (e.g. "Bash(git *)
      Edit")
  --append-system-prompt <prompt>       Append a system prompt to the default
                                        system prompt
  --autocompact <auto|tokens>           Auto-compact window size (auto, or
                                        100k–1M tokens)
  --ax-screen-reader                    Render screen-reader friendly output
                                        (flat text, no decorative borders or
                                        animations).
  --bg, --background                    Start the session in the background and
                                        return immediately. Prints the id that
                                        `claude attach`, `logs`, `stop` and `rm`
                                        take; `claude agents` lists them
  --bare                                Minimal mode: skip hooks, LSP, plugin
                                        sync, attribution, auto-memory,
                                        background prefetches, keychain reads,
                                        and CLAUDE.md auto-discovery. Sets
                                        CLAUDE_CODE_SIMPLE=1. Anthropic auth is
                                        strictly ANTHROPIC_API_KEY or
                                        apiKeyHelper via --settings (OAuth and
                                        keychain are never read). 3P providers
                                        (Bedrock/Vertex/Foundry) use their own
                                        credentials. Skills still resolve via
                                        /skill-name. Explicitly provide context
                                        via: --system-prompt[-file],
                                        --append-system-prompt[-file], --add-dir
                                        (CLAUDE.md dirs), --mcp-config,
                                        --settings, --agents, --plugin-dir.
  --betas <betas...>                    Beta headers to include in API requests
                                        (API key users only)
  --brief                               Enable SendUserMessage tool for
                                        agent-to-user communication
  --chrome                              Enable Claude in Chrome integration
  --cloud [description|session_id|url]  Create a cloud session with the given
                                        description, or attach to an existing
                                        one by session ID or claude.ai/code URL
  -c, --continue                        Continue the most recent conversation in
                                        the current directory
  --dangerously-skip-permissions        Bypass all permission checks.
                                        Recommended only for sandboxes with no
                                        internet access.
  -d, --debug [filter]                  Enable debug mode with optional category
                                        filtering (e.g., "api,hooks" or
                                        "!1p,!file")
  --debug-file <path>                   Write debug logs to a specific file path
                                        (implicitly enables debug mode)
  --disable-slash-commands              Disable all skills
  --disallowedTools, --disallowed-tools <tools...>
      Comma or space-separated list of tool names to deny (e.g. "Bash(git *)
      Edit")
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --environment <environment_id>        Create a new cloud session that runs on
                                        the given self-hosted environment
                                        (ccpool_...).
  --exclude-dynamic-system-prompt-sections
      Move per-machine sections (cwd, env info, memory paths, git status) from
      the system prompt into the first user message. Improves cross-user
      prompt-cache reuse. Only applies with the default system prompt (ignored
      with --system-prompt). (default: false)
  --fallback-model <model>              Enable automatic fallback to specified
                                        model(s) when the default model is
                                        overloaded or not available. Accepts a
                                        comma-separated list to try each in
                                        order. Re-tries the primary at the start
                                        of each user turn. (only works with
                                        --print)
  --file <specs...>                     File resources to download at startup.
                                        Format: file_id:relative_path (e.g.,
                                        --file file_abc:doc.txt
                                        file_def:img.png)
  --fork-session                        When resuming, create a new session ID
                                        instead of reusing the original (use
                                        with --resume or --continue)
  --forward-subagent-text               Forward subagent text and thinking
                                        blocks as assistant/user messages with
                                        parent_tool_use_id set (only works with
                                        --print and --output-format=stream-json)
  --from-pr [value]                     Resume a session linked to a PR by PR
                                        number/URL, or open interactive picker
                                        with optional search term
  -h, --help                            Display help for command
  --ide                                 Automatically connect to IDE on startup
                                        if exactly one valid IDE is available
  --include-hook-events                 Include all hook lifecycle events in the
                                        output stream (only works with
                                        --output-format=stream-json)
  --include-partial-messages            Include partial message chunks as they
                                        arrive (only works with --print and
                                        --output-format=stream-json)
  --input-format <format>               Input format (only works with --print):
                                        "text" (default), or "stream-json"
                                        (realtime streaming input) (choices:
                                        "text", "stream-json")
  --json-schema <schema>                JSON Schema for structured output
                                        validation. Example:
                                        {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}
  --max-budget-usd <amount>             Maximum dollar amount to spend on API
                                        calls (only works with --print)
  --mcp-config <configs...>             Load MCP servers from JSON files or
                                        strings (space-separated)
  --model <model>                       Model for the current session. Provide
                                        an alias for the latest model (e.g.
                                        'fable', 'opus', or 'sonnet') or a
                                        model's full name (e.g.
                                        'claude-fable-5').
  -n, --name <name>                     Set a display name for this session
                                        (shown in the prompt box, /resume
                                        picker, and terminal title)
  --no-chrome                           Disable Claude in Chrome integration
  --no-session-persistence              Disable session persistence - sessions
                                        will not be saved to disk and cannot be
                                        resumed (only works with --print)
  --output-format <format>              Output format (only works with --print):
                                        "text" (default), "json" (single
                                        result), or "stream-json" (realtime
                                        streaming) (choices: "text", "json",
                                        "stream-json")
  --permission-mode <mode>              Permission mode to use for the session
                                        (choices: "acceptEdits", "auto",
                                        "bypassPermissions", "manual",
                                        "dontAsk", "plan")
  --plugin-dir <path>                   Load a plugin from a directory or .zip
                                        for this session only (repeatable:
                                        --plugin-dir A --plugin-dir B.zip)
                                        (default: [])
  --plugin-url <url>                    Fetch a plugin .zip from a URL for this
                                        session only (repeatable: --plugin-url A
                                        --plugin-url B) (default: [])
  -p, --print                           Print response and exit (useful for
                                        pipes). Note: The workspace trust dialog
                                        is skipped when Claude is run in
                                        non-interactive mode (via -p, or when
                                        stdout is not a TTY, e.g. piped or
                                        redirected output). Only use this in
                                        directories you trust. Settings files
                                        that fail validation are silently
                                        ignored in this mode (no error dialog is
                                        shown).
  --prompt-suggestions [value]          Enable prompt suggestions. In print/SDK
                                        mode, emits a prompt_suggestion message
                                        after each turn with a predicted next
                                        user prompt (choices: "true", "false",
                                        "1", "0", "yes", "no", "on", "off",
                                        preset: "true")
  --remote-control [name]               Start an interactive session with Remote
                                        Control enabled (optionally named)
  --remote-control-session-name-prefix <prefix>
      Prefix for auto-generated Remote Control session names (default: hostname)
  --replay-user-messages                Re-emit user messages from stdin back on
                                        stdout for acknowledgment (only works
                                        with --input-format=stream-json and
                                        --output-format=stream-json)
  --restricted                          Restricted mode: removes the built-in
                                        tools that run commands or code (Bash,
                                        PowerShell, REPL and the other
                                        code-running tools) and WebFetch unless
                                        --tools names them, and ignores user,
                                        project and local settings files
                                        (managed settings and --settings still
                                        apply; add --strict-mcp-config to skip
                                        MCP servers too). Also confines the file
                                        tools to the working directories
                                        (--add-dir included), refuses
                                        bypassPermissions, and lets only a
                                        person or the configured permission
                                        handler approve writes to settings, git
                                        and tool-configuration files.
  -r, --resume [value]                  Resume a conversation by session ID, or
                                        open interactive picker with optional
                                        search term
  --safe-mode                           Start with all customizations
                                        (CLAUDE.md, skills, plugins, hooks, MCP
                                        servers, custom commands and agents,
                                        output styles, workflows, custom themes,
                                        keybindings, and more) disabled — useful
                                        for troubleshooting a broken
                                        configuration. Admin-managed (policy)
                                        settings still apply. Auth, model
                                        selection, built-in tools, and
                                        permissions work normally. Sets
                                        CLAUDE_CODE_SAFE_MODE=1.
  --session-id <uuid>                   Use a specific session ID for the
                                        conversation (must be a valid UUID)
  --setting-sources <sources>           Comma-separated list of setting sources
                                        to load (user, project, local).
  --settings <file-or-json>             Path to a settings JSON file or a JSON
                                        string to load additional settings from
  --strict-mcp-config                   Only use MCP servers from --mcp-config,
                                        ignoring all other MCP configurations
  --system-prompt <prompt>              System prompt to use for the session
  --teleport [session]                  Resume a teleport session, optionally
                                        specify session ID
  --tmux                                Create a tmux session for the worktree
                                        (requires --worktree). Uses iTerm2
                                        native panes when available; use
                                        --tmux=classic for traditional tmux.
  --tools <tools...>                    Specify the list of available tools from
                                        the built-in set. Use "" to disable all
                                        tools, "default" to use all tools, or
                                        specify tool names (e.g.
                                        "Bash,Edit,Read").
  --verbose                             Override verbose mode setting from
                                        config
  -v, --version                         Output the version number
  -w, --worktree [name]                 Create a new git worktree for this
                                        session (optionally specify a name)

Commands:
  agents [options]                      Manage background agents
  attach <id>                           Open a background session in this
                                        terminal. <id> is the short id that
                                        `claude --bg` prints and `claude agents`
                                        lists
  auth                                  Manage authentication
  auto-mode                             Inspect or reset auto mode classifier
                                        configuration
  doctor                                Check the health of your Claude Code
                                        installation. Reads settings files in
                                        the current directory without a trust
                                        prompt. For a full checkup that can also
                                        fix issues, run /doctor in a session.
  gateway [options]                     Run the enterprise auth/telemetry
                                        gateway
  import [options] [source]             Import config from another AI coding
                                        agent into Claude Code
  install [options] [target]            Install Claude Code native build. Use
                                        [target] to specify version (stable,
                                        latest, or specific version)
  logs <id>                             Print a background session's recent
                                        terminal output
  mcp                                   Configure and manage MCP servers
  plugin|plugins                        Manage Claude Code plugins
  project                               Manage Claude Code project state
  respawn [options] [id]                Restart a background session, or all of
                                        them with --all, so it runs the current
                                        Claude Code version
  rm <id>                               Delete a background session, and its
                                        worktree when that is safe. Works on
                                        sessions that have already exited
  setup-token                           Set up a long-lived authentication token
                                        (requires Claude subscription)
  stop|kill <id>                        Stop a background session. Its
                                        conversation is kept: `claude attach
                                        <id>` opens it again, `claude --resume`
                                        works once it is stopped
  ultrareview [options] [target]        Run a cloud-hosted multi-agent code
                                        review of the current branch (or a PR
                                        number / base branch) and print the
                                        findings
  update|upgrade                        Check for updates and install if
                                        available's own text: 'the workspace trust dialog is skipped when Claude is run in non-interactive mode'), and on an untrusted folder this silently disables ALL frontmatter-registered hooks, with zero fallback, zero fail-closed behavior, and no signal visible outside a buried debug log line. This is NOT a scratch-clone-only artifact: the live repo's own persisted trust state in ~/.claude.json is currently hasTrustDialogAccepted=false. The architecture doc's own 3-round-corrected S2.2a fail-closed analysis covers only 'the hook script crashes/misbehaves once invoked' -- it never once considers 'the harness declines to invoke the hook at all,' so this gap was never surfaced or disclosed anywhere. The doc's own S2.1 explicitly required Development to 'empirically confirm it fires correctly for a Write/Edit call' before relying on this design; this was evidently not verified against a non-trusted/fresh environment (matching this project's own standard scratch-clone review convention), and Code Review's PASS did not catch it either. SECONDARY (2): (a) the Bash substring backstop's ' gdb'/' strace' entries (leading space required) never match when gdb/strace is the very first token of the command string with no preceding character -- e.g. tool_input.command='strace -p 1' is silently ALLOWED (verified directly against the shipped script); the identical command prefixed by anything, e.g. 'echo x; strace -p 1', correctly denies. This is a plain boundary bug, not one of the disclosed base64/heredoc/symlink adversarial bypasses -- reachable with zero evasion technique. (b) shlex.split() has quadratic-time blowup on a long single unquoted Bash command token (measured directly: 500K chars=5.4s, 1M chars=29.7s, 2M chars exceeds 30s) -- extrapolates to ~600s (the harness's own default PreToolUse hook timeout, confirmed in cli.js: TP=600000) around a ~4.5M-character single-token command, at which point the harness aborts/cancels the hook rather than receiving an explicit deny -- a hang-induced fail-open path never analyzed in S2.2a, and realistically reachable via the SAME large base64/heredoc payload already disclosed as defeating the substring check, compounding that known gap. MINOR (not blocking): /costs.html's 'Synchronous review' disclosure text (ops/control-center/generate_costs.py) still reads 'while TASK-017 stays paused (DEC-008)' -- stale now that DEC-010 resumed TASK-017 and this milestone's own Code Review already passed; the underlying cost_usd=NULL gap in reviewer_sync.py is real and remains, but the live disclosure text misrepresents why (implies it's tied to an active pause that has since ended). All 3 new synchronous reviewer routes (/api/tasks/<id>/review/{code,security,red-team}) themselves tested clean: real zero-tool invocation confirmed (agent_runtime._run_claude() passes --tools '' unconditionally, and a real Code Review run against TASK-017's own real handoff correctly REJECTed a truncated transcript per the mandatory truncation-forces-REJECT rule, writing a real reviewer_invocations row, rolling task status back correctly, and rendering correctly on tasks/<id>.html, reviews.html, pipeline.html, costs.html); unauthenticated POSTs get 403, missing/wrong CSRF token gets 403, invalid/nonexistent task IDs get 404, wrong review-gate status gets 400, wrong artifact path gets 400, PUT/DELETE get 501 -- all matching this project's established standard. No regression found on active-work.html/tasks/<id>.html/costs.html/meetings.html/overview.html/pipeline.html/agents.html/decisions.html/automation.html/releases.html/inbox.html (all 200). (returned to developer)
- TASK-023 — TASK-023 live sandboxing charter (architecture doc §7 item 7, Red Team's binding gateway contract §4/C1-C10, runbook §7b). Real /opt/claude-code/bin/claude 2.1.252 driven through the SHIPPED launch_developer_sandboxed.sh under real bwrap --unshare-all, against a throwaway Anthropic-shaped TLS upstream serving scripted tool_use turns so the agent issues real Read/Write/Edit/Grep/Bash calls inside the sandbox; plus containment probes run in the bwrap argv taken verbatim from a bash -x trace of the shipped wrapper. Exercised: (a) legitimate Developer work (edit, run tests, commit, handoff through the broker); (b) every closed vector in §6 (CLI auth material, .founder_credential.json, ptrace against a live host pid, raw sqlite3, network egress, egress allowlist read/modify, broker verb/task-id/identity abuse); the mandatory forking spend-ceiling assertion; the gateway contract; broker robustness/concurrency/restart; operator experience (timeouts, dead broker, dead gateway, 13 malformed-config cases, TLS failure); and a full regression run of all 9 shipped suites. Fake credentials and throwaway local upstreams only; no real credential material read and no request left this host. No ai-developer account, no groups, no sudoers, no units, no /run/ai-pipeline or /etc/ai-pipeline left behind; operations.sqlite3 byte-identical (25a60bd977312ede0bf0d16b95d00aa7). Full report: ops/reviews/qa-task023.md: 4 blocking. D1 THE SANDBOXED SESSION CANNOT DO A DEVELOPER'S JOB: with the shipped argv (no permission configuration anywhere in the milestone) every meaningful tool call is permission_denied in -p mode and there is no ask path - Write denied, python3 -c denied, running a test suite denied, git status/commit denied, and python3 ops/db/opsdb.py activity-log/handoff DENIED, so the broker is unreachable. The session still exits 0 with result.subtype=success, so nothing signals that the Developer did nothing. This is exactly the item §4.2 flagged as a required empirical verification and it was never run; interactive ask does not exist in -p mode and the default is deny. Localised: with one .claude/settings.local.json granting Bash/Write/Edit the same sandbox did all of it (edit, 'All checks passed', task-status and handoff both recorded through the broker), so containment is not the blocker - the missing grant is. Code Review round 5's real-binary run made ZERO tool calls, which is why six rounds missed this. D2 operations.sqlite3 IS A GIT-TRACKED FILE, so §4.4's mandated per-task git worktree materialises a byte-identical copy of the operational database inside every conformant sandbox, read-write. Falsifies §3 point 1, §6 bullet 6 and developer.md line 57. Reproduced live inside the shipped bind set: opened it, listed all 23 tables, read decisions/approvals/review_results; ran the exact command the broker drops (python3 ops/db/opsdb.py query 'SELECT id,title FROM decisions') and got real rows; then forged review_results(reviewed_by_agent='red-team',result='pass') and set risks.id=3 to resolved - both halves of Red Team Finding 1, routed around rather than bypassed. The write persists on the host and shows as 'M ops/db/operations.sqlite3', so it is committable on the branch a human merges. Not a root artifact: the checked-out copy is 0644 and runbook step 2's own chgrp/chmod g+rwX makes it group-writable by ai-developer by design. D3 GIT DOES NOT WORK INSIDE THE SANDBOX AT ALL: a linked worktree's .git is a file pointing at <repo>/.git/worktrees/<name>, which is not bind-mounted, so git status/add/commit all fail 'fatal: not a git repository' (rc=128). Charter (a)'s commit-within-the-worktree is structurally impossible and the handoff verb's base/head_commit_sha cannot be obtained. D4 RUNBOOK §7'S OWN SMOKE COMMAND uses --worktree-path /home/user/AI-Pipeline, binding the whole live repo read-write: verified from inside the sandbox that the LIVE operations.sqlite3 is present and writable (BEGIN IMMEDIATE succeeded) and .founder_credential.json is readable (contents printed - a planted placeholder, never a real credential), so §6's 'closed twice, independently' has only one layer left under the runbook's own instructions. NON-BLOCKING: N1 the broker has no rate or size ceiling (20x500KB activity-log rows accepted in 0.1s, DB 909KB->11.4MB) - Red Team's own argument for the gateway spend ceiling applies verbatim and nothing analogous was built; N2 the sandbox /tmp is a 7.9GB tmpfs backed by host RAM, undisclosed; N3 the broker hold-open DoS is unbounded, not 'one timeout' (4 holders delayed a legitimate caller 11.0s, repeatable forever); N4 .ai-pipeline-session/ holding the prompt and the broker capability token is written into the worktree and is NOT gitignored; N5 identity-pinning holds only because the sandbox uid differs from the broker's trusted set and nothing checks that (refused from uid 65534, but accepted with {'registered':true} when the uids collapse); N6 config-load failures print raw tracebacks; N7 the CONNECT reserve path is never charged against the spend ceiling; N8 developer.md carries two statements false as built; N9 known_limitations #4 can be narrowed (I enumerated the endpoint set from real tool-using sessions: only POST /v1/messages?beta=true and CONNECT api.anthropic.com:443). CODE REVIEW'S TWO CARRIED NOTES: check 73 is a genuine suite gap - as written an implementation returning the DAEMON's own uid would pass it AND checks 69-72, since the fork battery only proves non-resettability, never peer-ness; the property itself is real (two uids got independent 5-request buckets against one daemon running as a third uid). Runbook §6b's omitted table-full path is agreed unreachable with a uid key; one line suffices. (returned to developer)

## Current risks (open)
- [medium] Bash permissions cannot be scoped below the tool-category level (company, owner: cto)

## Founder decisions required
- none pending

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

