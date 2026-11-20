#!/usr/bin/env python3
import json
import sys
from pathlib import Path

DATA = json.loads("{\"message\": \"FAIL 0b7548c7da207f64: add constraint 'price_cli.py prints price table'\", \"needles\": [\"price_cli.py prints price table\"], \"claim\": {\"status\": \"threshold\", \"wants\": [\"constraints\"], \"failed\": [], \"constraints\": [\"price_cli.py prints price table\"], \"done_when\": []}}")
WANTS = {'mission', 'phase', 'constraints', 'done_when', 'workspace'}

def texts(value):
    if not isinstance(value, list):
        return []
    found = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in found:
            found.append(text)
    found.sort()
    return found

def payload(doc):
    if not isinstance(doc, dict):
        return None
    status = doc.get('status')
    if status not in {'done', 'blocked', 'threshold'}:
        return None
    inner = doc.get('residual')
    if not isinstance(inner, dict):
        return None
    raw = inner.get('wants_to_change') or []
    if not isinstance(raw, list):
        raw = []
    wants = texts([item for item in raw if item in WANTS])
    patch = inner.get('proposed_patch') or {}
    if not isinstance(patch, dict):
        return None
    failed = texts(patch.get('requirements_failed'))
    constraints = texts(patch.get('constraints+'))
    done_when = texts(patch.get('done_when+'))
    if status == 'done' and not failed:
        return None
    if not (wants or failed or constraints or done_when):
        return None
    return {
        'status': status,
        'wants': wants,
        'failed': failed,
        'constraints': constraints,
        'done_when': done_when,
    }

def homes(root):
    of = root / '.orderfield'
    fields = of / 'fields'
    found = []
    if fields.is_dir() and not fields.is_symlink():
        for home in sorted(p for p in fields.iterdir() if p.is_dir() and not p.is_symlink()):
            order = home / 'ORDER.json'
            if order.is_file() and not order.is_symlink():
                found.append(home)
    if found:
        return found
    if (of / 'ORDER.json').is_file() and not (of / 'ORDER.json').is_symlink():
        return [of]
    return []

def order_text(root):
    parts = []
    for home in homes(root):
        try:
            doc = json.loads((home / 'ORDER.json').read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        for key in ('constraints', 'done_when'):
            for item in doc.get(key) or []:
                parts.append(str(item))
    return '\n'.join(parts)

def matched(root):
    for home in homes(root):
        waves = home / 'waves'
        if not waves.is_dir() or waves.is_symlink():
            continue
        for wave in waves.iterdir():
            residuals = wave / 'residuals'
            if not wave.is_dir() or wave.is_symlink() or not residuals.is_dir() or residuals.is_symlink():
                continue
            for path in residuals.glob('*.json'):
                if path.is_symlink():
                    continue
                try:
                    doc = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    continue
                if payload(doc) == DATA['claim']:
                    return True
    return False

def main():
    root = Path(__file__).resolve().parents[2]
    needles = DATA['needles']
    if needles:
        text = order_text(root)
        if any(needle not in text for needle in needles):
            print(DATA['message'], file=sys.stderr)
            return 1
        return 0
    if matched(root):
        print(DATA['message'], file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
