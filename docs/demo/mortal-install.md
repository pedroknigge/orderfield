# One sitting: mortal install

A human lands a verified install and sees the disk contract. Not a daemon. Not pip.

> Hub: [AGENTS.md](../../AGENTS.md) · Pin recipe: [README.md](../../README.md#install) · Publish: [PUBLISH.md](../../PUBLISH.md) · Doctor: [troubleshooting.md](../troubleshooting.md#of-doctor)

`install.sh` already copies the skill and points `of` at the **installed** kernel. `of doctor` already names kernel + skills. This page is the one sitting that ties those together. Do not invent a second installer.

## Land it

From a checkout or an extracted, SHA-256-verified release tree:

```bash
bash docs/demo/mortal-install.sh --global
```

Hermetic look (does not touch `$HOME`):

```bash
bash docs/demo/mortal-install.sh --root "$(mktemp -d)"
```

The script calls `install.sh`, then the installed `of doctor` from an empty workdir. Exit 0 only when doctor prints `ok` (kernel + skills). It then names the disk contract: `.orderfield/` is the session; `of resume` is the next verb; no process supervisor, no `of merge`.

## No tree yet

Do not pipe unsigned `main`. Use the tag-pinned SHA-256 recipe on [README.md](../../README.md#install) / [PUBLISH.md](../../PUBLISH.md), then:

```bash
of doctor
```

`doctor        ok` is green. Skill `SKEW` alone is `WARN` / exit 0 — `bash install.sh --global`. Field FAIL is leftover ACTIVE/stub/open-field packs, not a missing install. Closed-field historical packs are informational.

If this install is behind a newer release, doctor asks at most once a day. On yes: `ORDERFIELD_VERSION=<ver> bash install.sh --global --from-release` (GitHub tag + SHA256SUMS). Consent, not a silent auto-update.

`npx skills add` installs skill markdown. It does not create the `of` CLI. Classic `install.sh` is the pin path.

## After green

The 90-second amnesia case: [README.md](README.md). A long mission: [long-mission.md](../long-mission.md). Do not open a field unless the work will not fit one context.

## What this is not

Not a process supervisor. Not a bot org. Not `RUNTIME_OWNERSHIP`. Not a fake token budget. Not `of merge`. The harness starts processes. The field holds the plan.

## Proof

`tests/test_packaging.py` `MortalInstallDemo` runs `--root` and requires `doctor        ok` plus the disk-contract lines. Existing `InstallScript` / `InstallPin` stay.
