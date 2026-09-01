"""Integration helpers for path checking."""
from typing import Any

def update_path_owners_index(state: dict[str, Any], wave: int, packets: list[dict[str, Any]]) -> None:
    """Update the O(1) path_index in state during integration."""
    path_index = state.setdefault("path_index", {})
    from of.pack import packet_owns_paths
    for packet in packets:
        child_id = str(packet.get("child_id") or "?")
        for owned in packet_owns_paths(packet):
            parts = owned.split("/")
            # exact match
            node = path_index.setdefault(owned, {"exact": [], "descendants": []})
            node["exact"].append({
                "child_id": child_id,
                "wave": int(wave),
                "owned_path": owned
            })
            # descendants for prefixes
            for i in range(1, len(parts)):
                prefix = "/".join(parts[:i])
                pnode = path_index.setdefault(prefix, {"exact": [], "descendants": []})
                pnode["descendants"].append({
                    "child_id": child_id,
                    "wave": int(wave),
                    "owned_path": owned
                })
