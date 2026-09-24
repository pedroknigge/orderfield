"""Inject --orden-only for plain of init/new in tests."""
from __future__ import annotations


def with_orden_only(*args: str) -> list[str]:
    """Append --orden-only to init/new unless Campo or orden-only is explicit."""
    out = list(args)
    i = 0
    while i < len(out):
        tok = out[i]
        if tok == "--json":
            i += 1
            continue
        if tok == "--field" and i + 1 < len(out):
            i += 2
            continue
        break
    if i < len(out) and out[i] in {"init", "new"}:
        if "--campo" not in out and not any(
            tok.startswith("--orden-only") for tok in out
        ):
            out.extend(["--orden-only=user", "--orden-reason", "test fixture: plain Orden"])
    return out
