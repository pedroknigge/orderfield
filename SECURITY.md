# Security

Orderfield is a local stdlib CLI plus an Agent Skill. It is a cooperative contract, not an OS jail and not a process supervisor. This page is scope and how to report. It is not a bounty, not an SLA, and not a promise that children cannot write the tree.

A cut, a resume, a different host — the threat model does not change. The results do not have to change.

Threat model (what `of` stops vs what it honestly does not): [docs/external-brief.md](docs/external-brief.md#threat-model). Out of product scope: [docs/audit/out-of-scope.md](docs/audit/out-of-scope.md).

## Supported versions

The current tagged release (`VERSION`, GitHub `vX.Y.Z`) is the line that receives fixes. Older tags are not a supported security branch. Docs-only trees without a proven cut are not a release.

## In scope

Report a vulnerability when a **crafted input or install path** in this repo can, on a machine that runs `of` as intended:

- escalate privilege past the documented spawn allowlist / `OF_TRUST` defaults
- leak secrets through residuals, pulse, issue drafts, logs, or install
- forge close, WAL, lock, or child-provenance so a public claim lands without the leader
- skip the tag-pinned SHA-256 install pin

Those are defects in Orderfield. Use this page.

## Out of scope

These are not security reports. Do not file them here.

- A disobedient child or leader writing product files without `of` — protocol, not a jail
- Harness bugs in claude / codex / cursor / grok / agy / orca / qwen / generic `OF_AGENT`
- PATH present ≠ login (`of detect` / `of doctor`)
- Reserved accounting (`RUNTIME_OWNERSHIP`, `budget.tokens`)
- Child did not finish, SPEC incomplete, product tests red, “user is stuck”
- CPython stdlib or GitHub Actions CVEs without a kernel-specific exploit path

Public kernel defects that are **already visible** (invalid schema, WAL incoherent, contrast self-contradiction, docs vs code) stay on [CONTRIBUTING.md](CONTRIBUTING.md) / `of issue` after HITL. That path is public. Do not use it for an undisclosed vulnerability.

## How to report

**Prefer a private GitHub Security Advisory** on [pedroknigge/orderfield](https://github.com/pedroknigge/orderfield/security/advisories/new).

Do not open a public issue, PR, or `of issue` for an unpatched vulnerability. Do not paste tokens, private transcripts, or field residuals.

Include:

1. Affected `VERSION` / tag (or commit)
2. What an attacker who is not the operator can do
3. Repro that stays on this repo’s surfaces (`of`, `install.sh`, schemas, spawn env)
4. Whether the report needs a coordinated disclose window

There is no bug bounty. There is no promised response time. A silent or later-edit reply is not consent to publish.

## What this is not

Not a sandbox guarantee. Not `of merge`. Not a supervisor. Worktree and process bounds are honesty surfaces. Cloning an open `.orderfield/` with an installed skill still auto-continues — operator risk, not an escape.
