# Mega-plan: hospital protocol bed scheduler

Incoming Grill-me / documentation-manager shape. Every requirement
section below must become a wave/packet. Meta headings are not sections.

## Why this exists

Pedro (2026-09-19): OF’s next level is how we form the ORDER. Digest
this plan fully — nothing orphaned outside waves/packets. Deep thinking
belongs when writing the ORDER. Child slices stay medium.

## AUTH-001 Login boundary

Clean architecture: auth stays behind a port. Vertical slice owns
`src/auth.py`. Tracer-bullet wave 1 must cross this boundary.

## STORE-001 Persist occupancy

Store writes occupancy JSON under `src/store.py`. Blast-radius is that
file plus its tests. Do not invent a second ledger.

## HTTP-001 Public status

Public `/status` and `/health` in `src/http_api.py`. Prove-it-works at
the surface. Pair with AUTH-001 on the tracer wave when thin E2E needs it.

## CLI-001 Print occupancy

`python -m beds status` exits 0. owns `src/cli.py`. Sequence as a
verifiable unit after STORE-001.

## Out of scope

New supervisor. Action Fusion. RSI harness self-rewrite. Rewriting
user docs without ask.
