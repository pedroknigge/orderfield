# Performance — wave wall-clock

No database. No HTTP server. Load is how long a wave takes at the caps you actually use.

Measure pack→collect with handoff spawn. Residual `metrics.*` are uncertainty, not SLOs.

Caps in `ORDER.caps` throttle. Reserved accounting is not performance data.

A cut, a resume, a different model — the probe is still wall-clock. The results do not have to change.

Orderfield has no database and no HTTP server. The only load that matters is **how long a wave takes** at the child caps you actually use.

## Published probe

`PackCollectWallClock` on `of eval --kernel` times **N=4** (default `max_children`) pack → generic handoff spawn → done residuals → collect. It fails above 30s as a disk-thrash smoke. It is not a product SLO, not `budget.seconds` (spawn kill), and not the 7-day `packed_age` SLA. Residual `metrics.*` stay uncertainty.

```bash
python3 -m unittest tests.test_kernel_pack.PackCollectWallClock
```

There is no kernel soft-warn and no release-notes threshold. A slow loop is a CI fail, not a stderr note.

## Measure

Operator recipe (same loop as the probe; exclude agent think time). From a throwaway worktree (or temp dir) with `of` on PATH:

```bash
# N=4 (default max_children)
ROOT=$(mktemp -d)
cd "$ROOT"
of init --mission "perf probe" --phase explore --source "noop pack collect probe"
START=$(python3 -c 'import time; print(time.time())')
for i in 1 2 3 4; do
  of pack --slice "noop slice $i" --role explorer --child-id "c$i"
  of spawn --adapter generic --packet ".orderfield/waves/001/packets/c$i.json"
done
python3 - <<'EOF'
import hashlib, json, os
from pathlib import Path
for i in range(1, 5):
    cid = f"c{i}"
    packet = json.load(open(f".orderfield/waves/001/packets/{cid}.json"))
    ref = f".orderfield/work/scratch/{cid}/notes.md"
    os.makedirs(os.path.dirname(ref), exist_ok=True)
    open(ref, "w").write(f"{cid} mapped\n")
    digest = hashlib.sha256(open(ref, "rb").read()).hexdigest()
    residual = {k: packet[k] for k in (
        "packet_id", "packet_hash", "order_id", "order_rev", "wave", "child_id", "role"
    )}
    residual.update(
        status="done",
        result_ref=ref,
        residual={
            "wants_to_change": [],
            "evidence": (
                f"{cid}: mapped\nartifact_sha: {digest}\n"
                f"rollback: git checkout -- {ref}"
            ),
            "proposed_patch": None,
        },
        metrics={
            "uncertainty": 0.1,
            "divergence": 0.0,
            "tool_failures": 0,
            "novelty": False,
        },
    )
    dest = Path(f".orderfield/waves/001/residuals/{cid}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(residual, indent=2) + "\n", encoding="utf-8")
EOF
of collect --wave 1
python3 -c "import time; print('elapsed_s', round(time.time()-float('$START'), 3))"
```

Repeat with N=16 only after raising `caps.max_children` via `of patch` (or a test ORDER). Record wall-clock for **pack→collect**. That optional loop is not CI-gated.

## Product note

Realistic load for this package is “a handful of parallel children,” not thousands of rows. Caps in `ORDER.caps` are the primary throttle.
