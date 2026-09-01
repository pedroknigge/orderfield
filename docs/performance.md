# Performance — wave wall-clock

**STAR**

- **Situation:** This kernel has no database and no HTTP server; load is wave wall-clock at real caps.
- **Task:** Give a probe for pack→collect time with handoff-style spawn, not fake telemetry.
- **Action:** Measure from a throwaway tree; treat residual `metrics.*` as uncertainty signals, not SLOs.
- **Result:** Caps in `ORDER.caps` stay the throttle; reserved accounting is not performance data.

Orderfield has no database and no HTTP server. The only load that matters is **how long a wave takes** at the child caps you actually use.

## Measure

From a throwaway worktree (or temp dir) with `of` on PATH:

```bash
# N=4 (default max_children)
ROOT=$(mktemp -d)
cd "$ROOT"
of init --mission "perf probe" --phase explore
START=$(python3 -c 'import time; print(time.time())')
for i in 1 2 3 4; do
  of pack --slice "noop slice $i" --role explorer --child-id "c$i"
done
# handoff-style spawn (no external agent binary required)
for i in 1 2 3 4; do
  of spawn --adapter generic --packet ".orderfield/waves/001/packets/c$i.json" || true
done
# drop done fixtures or write minimal residuals, then:
# of collect --wave 1 && of integrate --wave 1
python3 -c "import time; print('elapsed_s', round(time.time()-float('$START'), 3))"
```

Repeat with N=16 only after raising `caps.max_children` via `of patch` (or a test ORDER). Record wall-clock for **pack→collect** (exclude agent think time if children are mocked/handoff).

## Soft warns

| Signal | Guidance |
|--------|----------|
| Wave packet count &gt; `max_children` | Refuse at pack (kernel already caps) |
| Pack→collect wall-clock &gt; 30s for N≤4 with handoff-only spawn | Investigate disk thrash or accidental agent waits |
| Pack→collect wall-clock &gt; 120s for N=16 handoff-only | Soft warn in release notes; consider smaller waves |

Regime residual `metrics.*` fields are **uncertainty / divergence signals**, not latency SLOs. Do not treat them as performance telemetry.

## Product note

Realistic load for this package is “a handful of parallel children,” not thousands of rows. Caps in `ORDER.caps` are the primary throttle.
