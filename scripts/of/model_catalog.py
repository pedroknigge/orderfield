"""Advisory living model catalog. Skill/leader only.

Not a router, not IQ ranks, not budget.tokens.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REL_JSON = Path("docs") / "model-catalog.json"
REL_MD = Path("docs") / "model-catalog.md"
TIERS = ("cheap", "mid", "frontier", "unknown")
ROW_KEYS = (
    "harness",
    "model_id",
    "tier_hint",
    "price_public",
    "notes",
    "last_checked",
)
FORBIDDEN = ("iq", "iq_rank", "intelligence_rank", "elo")


class ModelCatalog:
    """Load and lint the in-repo catalog. Static methods only."""

    @staticmethod
    def json_path(root: Path) -> Path:
        return Path(root) / REL_JSON

    @staticmethod
    def md_path(root: Path) -> Path:
        return Path(root) / REL_MD

    @staticmethod
    def load(root: Path) -> dict[str, Any]:
        path = ModelCatalog.json_path(root)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("model-catalog.json must be an object")
        return raw

    @staticmethod
    def models(doc: dict[str, Any]) -> list[dict[str, Any]]:
        rows = doc.get("models")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def sources(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for item in doc.get("sources") or []:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
        return out

    @staticmethod
    def md_keys(text: str) -> list[tuple[str, str]]:
        start = text.find("## Living table")
        if start < 0:
            return []
        keys: list[tuple[str, str]] = []
        for line in text[start:].splitlines():
            if not line.startswith("| "):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            if cells[0] in {"harness", "---"} or cells[0].startswith("---"):
                continue
            keys.append((cells[0], cells[1]))
        return keys

    @staticmethod
    def doctor_lines() -> list[str]:
        return [
            f"{REL_MD.as_posix()} (advisory; not budget.tokens)",
        ]

    @staticmethod
    def errors(root: Path) -> list[str]:
        path = Path(root)
        errors: list[str] = []
        json_path = ModelCatalog.json_path(path)
        md_path = ModelCatalog.md_path(path)
        if not json_path.is_file():
            errors.append(f"missing {REL_JSON}")
        if not md_path.is_file():
            errors.append(f"missing {REL_MD}")
        if errors:
            return errors
        try:
            doc = ModelCatalog.load(path)
        except (OSError, ValueError) as exc:
            return [f"model-catalog.json: {exc}"]
        if doc.get("kind") != "model-catalog":
            errors.append("kind must be model-catalog")
        sources = ModelCatalog.sources(doc)
        models = ModelCatalog.models(doc)
        if not models:
            errors.append("models[] empty")
        seen: set[tuple[str, str]] = set()
        for i, row in enumerate(models):
            prefix = f"models[{i}]"
            for key in ROW_KEYS:
                if not str(row.get(key) or "").strip():
                    errors.append(f"{prefix} missing {key}")
            tier = str(row.get("tier_hint") or "")
            if tier and tier not in TIERS:
                errors.append(f"{prefix} tier_hint {tier!r}")
            for bad in FORBIDDEN:
                if bad in row:
                    errors.append(f"{prefix} forbids {bad}")
            key = (str(row.get("harness") or ""), str(row.get("model_id") or ""))
            if key in seen:
                errors.append(f"duplicate {key[0]} {key[1]}")
            seen.add(key)
            known = bool(row.get("price_known"))
            price = str(row.get("price_public") or "").strip()
            source_id = str(row.get("source_id") or "").strip()
            if known:
                if price.lower() == "unknown":
                    errors.append(f"{prefix} known price cannot be unknown")
                if not source_id or source_id not in sources:
                    errors.append(f"{prefix} known price needs source_id")
                elif not str(sources[source_id].get("url") or "").startswith(
                    "https://"
                ):
                    errors.append(f"{prefix} source url missing")
            elif price.lower() != "unknown":
                errors.append(f"{prefix} unknown price must be 'unknown'")
        md_keys = ModelCatalog.md_keys(md_path.read_text(encoding="utf-8"))
        json_keys = [
            (str(row.get("harness") or ""), str(row.get("model_id") or ""))
            for row in models
        ]
        if md_keys != json_keys:
            errors.append("living table keys != model-catalog.json")
        folded = md_path.read_text(encoding="utf-8").casefold()
        if "budget.tokens" not in folded:
            errors.append("model-catalog.md must name reserved budget.tokens")
        if "smarter is not always costlier" not in folded:
            errors.append("model-catalog.md must teach smarter≠costlier")
        return errors
