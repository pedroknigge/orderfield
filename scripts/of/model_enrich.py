"""Advisory tier/price overlay for live model discovery (stdlib only).

Seed catalog supplies verified rows; inference fills tier gaps from discovery
fields; optional OpenRouter refresh adds fetched prices. Never invents price on
inference. Refresh failure never raises.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from of.field import skill_root
from of.model_catalog import TIERS, ModelCatalog

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

CHEAP_TOKENS = frozenset(
    "mini flash haiku lite luna build nano small fast".split()
)
FRONTIER_TOKENS = frozenset(
    "opus sol astra pro ultra flagship frontier fable powerful capable".split()
)
RECOMMENDED_LABEL = re.compile(r"\b(default|recommended)\b", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def price_cache_path() -> Path:
    override = (os.environ.get("OF_MODEL_PRICE_CACHE") or "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "orderfield" / "model-prices.json"


def _seed_index(root: Path) -> tuple[dict[tuple[str, str], dict], dict[str, dict]]:
    try:
        doc = ModelCatalog.load(root)
    except (OSError, ValueError):
        return {}, {}
    sources = ModelCatalog.sources(doc)
    by_key: dict[tuple[str, str], dict] = {}
    for row in ModelCatalog.models(doc):
        harness = str(row.get("harness") or "")
        model_id = str(row.get("model_id") or "")
        if not harness or not model_id or model_id == "(user-config)":
            continue
        by_key[(harness, model_id)] = row
    return by_key, sources


def _seed_lookup(
    by_key: dict[tuple[str, str], dict],
    harness: str,
    model_id: str,
    resolved: str | None,
) -> dict[str, Any] | None:
    for key in ((harness, model_id), (harness, resolved or "")):
        if key[1] and key in by_key:
            return by_key[key]
    return None


def _token_tier(text: str) -> str | None:
    words = set(re.split(r"[^a-z0-9]+", text.casefold()))
    if words & CHEAP_TOKENS:
        return "cheap"
    if words & FRONTIER_TOKENS:
        return "frontier"
    return None


def _family_tier(
    harness: str,
    model_id: str,
    resolved: str,
    by_key: dict[tuple[str, str], dict],
) -> tuple[str, str] | None:
    best: tuple[str, str] | None = None
    best_len = 0
    needle = (resolved or model_id).casefold()
    for (h, mid), srow in by_key.items():
        if h != harness:
            continue
        stem = mid.casefold()
        if len(stem) < 3:
            continue
        if stem in needle or needle in stem:
            tier = str(srow.get("tier_hint") or "unknown")
            if tier in TIERS and tier != "unknown" and len(stem) > best_len:
                best = (tier, "inferred")
                best_len = len(stem)
    return best


def _infer_tier(
    harness: str,
    row: dict,
    peers: list[dict],
    seed_row: dict | None,
    by_key: dict[tuple[str, str], dict],
) -> tuple[str, str]:
    if seed_row:
        tier = str(seed_row.get("tier_hint") or "unknown")
        if tier in TIERS and tier != "unknown":
            return tier, "seed"
    model_id = str(row.get("model_id") or "")
    resolved = str(row.get("resolved_model") or "")
    family = _family_tier(harness, model_id, resolved, by_key)
    if family:
        return family
    blob = " ".join(
        part
        for part in (
            model_id,
            resolved,
            str(row.get("display_name") or ""),
            str(row.get("description") or ""),
        )
        if part
    )
    token = _token_tier(blob)
    if token:
        return token, "inferred"
    upgrade = str(row.get("recommendation") or "").strip()
    if upgrade:
        return "mid", "inferred"
    if any(str(other.get("recommendation") or "") == model_id for other in peers):
        return "frontier", "inferred"
    display = str(row.get("display_name") or "")
    if RECOMMENDED_LABEL.search(display):
        return "mid", "inferred"
    if row.get("is_default") is True:
        return "mid", "inferred"
    defaults = [p for p in peers if p.get("is_default") is True]
    if defaults and row not in defaults and len(peers) <= 8:
        return "cheap", "inferred"
    return "unknown", "unknown"


def _format_mtok(prompt: str, completion: str) -> str:
    try:
        pin = float(prompt) * 1_000_000
        pout = float(completion) * 1_000_000
    except (TypeError, ValueError):
        return "unknown"
    return f"${pin:g} / ${pout:g} per MTok in/out"


def load_price_cache() -> dict[str, Any]:
    path = price_cache_path()
    empty: dict[str, Any] = {
        "v": 1,
        "source_url": OPENROUTER_MODELS_URL,
        "fetched_at": None,
        "models": {},
    }
    if not path.is_file():
        return empty
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(raw, dict):
        return empty
    if not isinstance(raw.get("models"), dict):
        raw["models"] = {}
    return raw


def save_price_cache(doc: dict[str, Any]) -> None:
    path = price_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def refresh_price_cache(url: str = OPENROUTER_MODELS_URL) -> dict[str, Any]:
    """Fetch public model pricing. On failure return previous cache, never raise."""
    prior = load_price_cache()
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "orderfield-models/1", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return prior
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return prior
    models: dict[str, dict[str, str]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        pricing = item.get("pricing")
        if not isinstance(model_id, str) or not isinstance(pricing, dict):
            continue
        prompt = pricing.get("prompt")
        completion = pricing.get("completion")
        if prompt is None or completion is None:
            continue
        models[model_id] = {"prompt": str(prompt), "completion": str(completion)}
    if not models:
        return prior
    doc = {
        "v": 1,
        "kind": "model-price-cache",
        "source_url": url,
        "fetched_at": _utc_now(),
        "models": models,
    }
    save_price_cache(doc)
    return doc


def _match_fetched(
    model_id: str,
    resolved: str | None,
    cache: dict[str, Any],
) -> tuple[str, str] | None:
    models = cache.get("models")
    if not isinstance(models, dict) or not models:
        return None
    url = str(cache.get("source_url") or OPENROUTER_MODELS_URL)
    fetched_at = str(cache.get("fetched_at") or "")
    if not fetched_at:
        return None
    source = f"fetched:{url}@{fetched_at}"
    candidates: list[str] = []
    for part in (resolved, model_id):
        if part:
            candidates.append(part.casefold())
    for key, pricing in models.items():
        kl = key.casefold()
        tail = kl.rsplit("/", 1)[-1]
        for cand in candidates:
            if cand == kl or cand == tail or kl.endswith("/" + cand):
                price = _format_mtok(pricing.get("prompt", ""), pricing.get("completion", ""))
                if price != "unknown":
                    return price, source
    return None


def _seed_price(seed_row: dict | None, sources: dict[str, dict]) -> tuple[str, str]:
    if not seed_row or not seed_row.get("price_known"):
        return "unknown", "unknown"
    price = str(seed_row.get("price_public") or "").strip()
    if not price or price.casefold() == "unknown":
        return "unknown", "unknown"
    source_id = str(seed_row.get("source_id") or "").strip()
    ref = sources.get(source_id, {})
    url = str(ref.get("url") or "").strip()
    checked = str(ref.get("checked") or seed_row.get("last_checked") or "").strip()
    if url.startswith("https://") and checked:
        return price, f"seed:{url}@{checked}"
    return price, "seed"


def enrich_models(
    root: Path | None,
    harness: str,
    rows: list[dict],
    *,
    refresh_prices: bool = False,
) -> list[dict]:
    """Attach tier_hint and price_public with explicit provenance sources."""
    if not rows:
        return rows
    cat_root = root or skill_root()
    by_key, sources = _seed_index(cat_root)
    cache = refresh_price_cache() if refresh_prices else load_price_cache()
    if refresh_prices and not cache.get("fetched_at"):
        cache = load_price_cache()
    out: list[dict] = []
    for row in rows:
        merged = dict(row)
        model_id = str(row.get("model_id") or "")
        resolved = row.get("resolved_model") if isinstance(row.get("resolved_model"), str) else None
        seed_row = _seed_lookup(by_key, harness, model_id, resolved)
        tier, tier_src = _infer_tier(harness, row, rows, seed_row, by_key)
        price, price_src = _seed_price(seed_row, sources)
        if price == "unknown":
            fetched = _match_fetched(model_id, resolved, cache)
            if fetched:
                price, price_src = fetched
        merged["tier_hint"] = tier
        merged["tier_source"] = tier_src
        merged["price_public"] = price
        merged["price_source"] = price_src
        out.append(merged)
    return out
