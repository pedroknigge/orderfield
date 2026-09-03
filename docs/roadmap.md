# Roadmap

The current line is 0.7.2. Accounting and `scale_up` stay reserved. That is the slow decision.

This page indexes what shipped and what must not be invented. Not a second regime.

`RUNTIME_OWNERSHIP` lives in `scripts/of/regime.py`. Test C is harness QA, not kernel CI.

A cut, a resume, a different model — the deferred work is still deferred. The results do not have to change.

> Hub: [AGENTS.md](../AGENTS.md) · Current architecture: [architecture.md](architecture.md) · Release history: [CHANGELOG.md](../CHANGELOG.md)

**Status:** Shipped · **Current release line:** `0.7.2`

Orderfield remains a portable contract kernel: the harness owns processes, while ORDER, packets, residuals, validation, and regime decisions remain disk-backed and harness-neutral. The 0.5.0 operational contract preserves that boundary; runtime accounting stays reserved.

## 0.7.2 — Vibe-Proof v0.9.5 P1 (WAL writer / sibling residual / 0.7.2 identity)

- Writer rematerialize of CURRENT before inherit. `packet_residual_file` sole residual resolver including unpack/stale. Issue title/search bound. Full-runtime unused-import checker. Not a new regime.

## 0.7.1 — Vibe-Proof Deep P1/P2 (LEARN-002 / ISSUE / WAL-002 / JSON / SCOPE)

- Spawn pid/starttime registry plus unauthenticated provenance. `of issue` uses the same child detection and a bounded scratch body. CURRENT generation is the sole read after flip. JSON stderr is all events. Out-of-scope auditor items are recorded so they are not re-scored. Not a new regime.

## 0.7.0 — Vibe-Proof Deep P1 (LEARN / WAL / COST / INSTALL)

- Ancestor exec-env refuse for `of learn --protocol`/`--promote`. CURRENT-only WAL read view. Spawn cost disclaimer. Tag-pinned SHA-256 installer. Review-requirement config stays; independent review in merge history still unproven. Not a new regime.

## 0.6.9 — HITL `of issue` + sibling recovery + stay-on-run

- Public `of issue` always targets `pedroknigge/orderfield`; HITL then submit; children cannot submit. Sibling leftover `ORDER.json` no longer blocks `of new`. Canonical `--packet` resolves on sibling fields. Pulse `STALE` continues the same packet. Grok Bot contrast is docs, not a bot org. Not a new regime.

## 0.6.8 — P1 close + theater cut

- `OF_CHILD` closes the protocol-learning forge; field WAL (stage+MANIFEST+publish); pack tokens are 0 / `--tokens N>0` dies. `main` requires one approving review plus the five checks.
- Collect/integrate print owned-but-unverified (never auto-stamp). Constraint whitespace dedupe. PHASE.md splits mission vs phase. `--backlog-undone`. Compact render ORDER view. `of spec --add` writes the ID into SPEC.md. SLAVE comments are not the field diary. Not a new regime.

## Grok Bot contrast (protocol pick; not a bot org)

Grok Bot is an engineering org of persistent domain bots that manage cloud agents, share Notion, auto-merge, and poll P0 every 5 minutes. Orderfield is a disk-backed contract kernel. The two are not the same product. Managing 200 cloud agents is `RUNTIME_OWNERSHIP` in `scripts/of/regime.py` — reserved, not this path.

| Grok Bot pattern | Orderfield surface | Reserved kernel |
|---|---|---|
| Domain-owned persistent bots | `of pack --owns-path` / `--owns-requirement`; explorer/implementer/adversary/verifier/synthesizer | not a bot org chart |
| Leader manages coding agents | pack + `of spawn` / `of handoff`; residual `result_ref`; `of contrast` | no process supervisor, PIDs, cancellation, child supervision, `scale_up` |
| Complete feedback loop (screenshots) | SPEC + `done_when` + VERIFIED_CONTRACT; slogan evidence forbidden | no screenshot runtime |
| Shared Notion DB every 30 min | `of pulse`, `of resume` roster, `ORDER.backlog` | no Notion, no 30-min kernel poll |
| Ops bot (Jenny) | `of learn --protocol` after a real miss | no ops-bot regime |
| Nightly audits | `of new --mission` if asked | no 3 a.m. supervisor |
| P0 transcript every 5 min | tighter `--stale-min` / `budget.seconds` on a named packet | no 5-minute kernel loop |
| Auto-merge if confident | `of contrast` then human; merge stays GitHub | no `of merge` |

**Pick:** stay-on-the-run + written contrast. Pulse `STALE` → continue the same packet this turn (`of handoff` / `of spawn`); do not unpack by default; do not wait forever; not a daemon. No bot org, no Notion, no cloud-agent manager, no auto-merge command, no process supervisor. `RUNTIME_OWNERSHIP` stays reserved. VERSION is not bumped here (SHIP-001 is leader after contrast).

## 0.6.7 — vibe-proof hardening

- `OF_TRUST` is authoritative for every adapter (`conservative` default; only `yolo` emits bypass flags). Spawn env is an allowlist (`OF_SPAWN_ENV`); children get no stdin and their own process group.
- `spec` and `checkpoint` join `MUTATING_COMMANDS`. Learnings carry provenance; bare `of learn` is field-local; `--protocol` is explicit.
- Error boundary: one-line `of: error: <kind>: <message>` (exit 1); `--json` `error` event; `OF_DEBUG=1` for tracebacks; Ctrl-C 130.
- Python 3.11 floor on every surface. CI pins Actions SHAs. README quickstart is a CI fixture. Not a new regime.

## 0.6.6 — sibling fields

- Several fields in one working tree: `of new`, `of fields`, `--field` / `OF_FIELD`.
- Resume roster (exit 2) when several open fields do not match this session. Foreign origin gate on `auto_continue`. `pulse` / `status` use the same roster.
- Cross-field in-flight `--owns-path` overlap dies at pack. Not a product-file locker. Not a TTY prompt. Not a new regime.
- First `of init` stays legacy `.orderfield/ORDER.json`. First `of new` promotes it under `fields/<id>/`.

## 0.6.5 — origin provenance

- Optional `ORDER.origin` `{harness, session_id?, recorded_at}` on the contract. Pointer, not transcript, not spawn pin, not `session.json`.
- `of init --origin` / `--session-id`, `OF_ORIGIN` / `OF_SESSION_ID`, `of patch --origin` (`-` clears). `of resume` / `of status` print one line when present.
- `pick_adapter` ignores origin. Kernel does not fetch harness sessions. Not a new regime.

## 0.6.4 — protocol learnings

- `of learn` (default `--protocol`) writes durable Orderfield lessons to the user cache; `--field` binds to this ORDER. `--list` / `--forget`.
- `of gc` keeps protocol; drops inapplicable field lessons. Child prompts get at most 8 protocol lines; not SPEC. Not a new regime.

## 0.6.2 — CLI command groups (form)

- `scripts/of/cli.py` → package `scripts/of/cli/` (`init_cmd`, `ops`, `wave`, `field_cmd`, `spec_cmd`). Parser + dispatch stay in `cli/__init__.py`.
- Public `of` / `scripts/of.py` / `import of` unchanged. Not a new regime.

## 0.6.1 — deictic go-ahead ingest (patch)

- Leader protocol: a `dale` / `do it` / `as discussed` is not SPEC. Expand the prior request into `--source`, or `of resume` → `next` on an open field.
- Kernel advisory on `init --source` / `spec --amend` / `--revise` when the text looks like a go-ahead; SPEC is still written.
- Not a new regime.

## 0.6.0 — form split (not a new regime)

- Kernel internals: `scripts/of/{field,spec,pack,regime,cli}.py`; public `of` / `scripts/of.py` unchanged vs 0.5.7.
- Positioning: README Compared-to, glossary, C4/mermaid, 90s demo (`docs/demo/README.md`).
- `install.sh` without `/dev/fd` process-substitution; `test_kernel.py` split by invariant class.
- Protocol unchanged. `scale_up` / `scale_across` / `budget.tokens` / `local_budget_pct` / inherited depth stay reserved. Test C is not kernel CI.

## 0.5.7 — eval CI + contrast recovery + Test C doc

- CI: `of eval --strict --kernel` after unittest (all matrix jobs).
- Recovery eval: `recovery/contrast-close-internal` (contrast → close gate).
- Optional harness QA: [recovery-test-c-harness-kill.md](audit/recovery-test-c-harness-kill.md) (real process kill; not kernel CI).

## 0.5.6 — Eve-inspired ops (evals, parked agents, discovery)

- `of eval` recovery fixtures (Quarry + Beacon) runnable in CI with `--strict`.
- `of resume` parked-agent listing (`parked_reason`, `agents_note`).
- Agent discovery index: [docs/agent-discovery.md](agent-discovery.md).
- Context control + events vocabulary docs.

## 0.5.0 — operational contract

### Harness and trust

- Qwen Code adapter: detect any Qwen CLI, use Qwen-owned headless argv, deliver a schema-valid residual, and default to safe non-escalated trust. Local/Ollama is a supported path, not a hardcoded default. Qwen support does not inherit another adapter's flags or approval model.
- Explicit trust profiles for adapter execution, with conservative defaults and a visible `OF_TRUST` override. Kernel verifies PATH/argv/residual; the harness promises approval, auth, and readiness.
- `of doctor` for local prerequisites, adapter command availability/version, writable field paths, schema availability, and lock capability. PATH presence remains distinct from authentication/readiness.

### Compatibility and recovery

- `of migrate` versioned rewrites for pre-0.4.2 packet/report/state artifacts. Recovery compatibility is explicit, versioned, and removable only with a documented migration path (`of migrate --list`).
- Optional `of worktree` helper for same-repo child isolation. It is opt-in and is not a process manager.
- Audit and log safety: redact secrets and approval material from argv previews/logs. `of retain` / `of gc` keep useful residuals and applicable learnings, drop inapplicable learnings, and dump garbage/logs/history older than 30 days, without copying private transcripts into the field.
- Terminology: protocol keys `workspace.writable_by_slaves` and `.orderfield/SLAVE.md` stay frozen. `of migrate` maps writable aliases onto the protocol key. Haken "slaved mode" remains contract language.
- Stale-wave recovery: a fully stale wave after a leader patch is recoverable with `of next-wave` without hand-editing ORDER; a complete stale wave may also collect/integrate.

### Runtime ownership decision

**Decision: reserve, do not implement.** Encoded as `RUNTIME_OWNERSHIP` / `RESERVED_REGIMES` in `scripts/of/regime.py`. `scale_up`, `scale_across`, `budget.tokens`, `local_budget_pct`, and inherited depth stay in schema for compatibility and are never used as accounting. `decide_regime` remaps a reserved regime to `hold`. Do not infer accounting from child-authored claims.

- Managed parallel lifecycle, process IDs, cancellation, and child supervision remain out of scope; adopting them would expand Orderfield beyond a contract kernel.

## Not in 0.5.4

No process supervisor, real token/depth accounting, or automatic `scale_up` ships in 0.5.4. Those surfaces stay reserved.

### Recovery validation (0.5.4 line — complete)

| Test | Kernel | Verdict | Report |
|------|--------|---------|--------|
| A — dirty wave (Quarry) | 0.5.3 | RECOVERY WITH MINOR FRICTION | [recovery-test-a-quarry.md](audit/recovery-test-a-quarry.md) |
| B — leader amnesia sim (Beacon) | 0.5.4 | RECOVERY CLEAN | [recovery-test-b-beacon.md](audit/recovery-test-b-beacon.md) |

Test A showed packets/residuals/disk beat stale session and chat memory. Test B showed the 0.5.4 recovery brief is sufficient for an amnesiac leader (simulated; same agent process).
