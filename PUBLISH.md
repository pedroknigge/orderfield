# Publish notes

Public repo: https://github.com/pedroknigge/orderfield

## Pre-publish gate

```bash
python3 -m unittest discover -s tests -v
./scripts/validate-skill.sh
```

Both must exit 0. Version must match across `VERSION`, `SKILL.md` metadata.version, and the latest `CHANGELOG.md` heading. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to change and what “done” means.

## Mortal install (after push)

```bash
npx skills add pedroknigge/orderfield -g -y -a '*'
# or
curl -fsSL https://raw.githubusercontent.com/pedroknigge/orderfield/main/install.sh | bash
```

Confirm:

```bash
test -f ~/.agents/skills/orderfield/SKILL.md && echo generic_ok
```
