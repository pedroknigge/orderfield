# Large init: sources, then one explorer

The leader does not pick tickets. On a large mission the first pack triages a sources list and proposes packs. Small fields (one or two slices, owners known) skip this.

Template: [evals/fixtures/sources-list.md](../../evals/fixtures/sources-list.md). Design: [sources-list.md](../design/sources-list.md). Proof: `SourcesTriagePath`.

`<owner>` is a short product slug, not a harness name.

```bash
of init --mission "…" --source "<verbatim brief>"
mkdir -p docs/plans/<owner>
cp evals/fixtures/sources-list.md docs/plans/<owner>/sources.md
# edit the rows: real paths and commands only
of pack \
  --slice "triage docs/plans/<owner>/sources.md; propose packs in result_ref; do not implement" \
  --role explorer \
  --child-id triage
```

`of pack` writes that packet on the live wave (`waves/001` on a fresh field). The explorer reads each row with the adapter's own tools and writes proposed packs (slice, role, owner) to `result_ref`. Leave `proposed_patch` null. The leader packs those proposals. The leader does not invent the list.

Rows are paths and commands (`gh run`, logs, dogfood paths, `gh issue list`). Do not require Claude Desktop, Claude Projects, or Tag.
