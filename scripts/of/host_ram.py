"""Host RAM suggest + once-per-field agent-band consent.

Reuse (design-first): AdapterHints consent+store; EvaluatorPacket once-at-init
ask; doctor section facts; SliceLint advisory notes; of init/patch writes.
caps.max_children stays the kernel bind — this module never hard-caps spawn.

Net-new: ORDER.agent_band + HostRam stdlib measure. Unavoidable because
done_when prose cannot drive pack hints, adapter_hints is model/tier, and
RAM is not already a doctor fact. No new verb. No psutil/WMI.
"""
from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from of.field import die

BANDS = ("1-4", "5-10", "10-50")
BAND_ALIASES = {
    "1-4": "1-4",
    "1–4": "1-4",
    "1—4": "1-4",
    "5-10": "5-10",
    "5–10": "5-10",
    "5—10": "5-10",
    "10-50": "10-50",
    "10–50": "10-50",
    "10—50": "10-50",
}
YES = frozenset({"yes", "true", "1", "on"})
NO = frozenset({"no", "false", "0", "off"})
GIB = 1024 ** 3
LINUX_MEMINFO = Path("/proc/meminfo")
CLOUD_NOTE = "leader host RAM is not a cloud/remote worker"
BUDGET_NOTE = "wave budget, not a spawn cap"
LOW_AVAIL_GB = 2.0


class HostRam:
    """Stdlib host RAM. Suggest a band. Never a kernel hard-cap."""

    @staticmethod
    def bytes_to_gb(n: int | None) -> float | None:
        if n is None or n < 0:
            return None
        return round(n / GIB, 1)

    @staticmethod
    def suggest_band(total_gb: float | None) -> str | None:
        """Pure GB → band. ≤8 → 1-4; ~16 → 5-10; ~32 / ≥64 → 10-50."""
        if total_gb is None:
            return None
        try:
            gb = float(total_gb)
        except (TypeError, ValueError):
            return None
        if gb < 0:
            return None
        if gb <= 8:
            return "1-4"
        if gb < 24:
            return "5-10"
        return "10-50"

    @staticmethod
    def parse_linux_meminfo(text: str) -> tuple[int | None, int | None]:
        total = None
        avail = None
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, rest = line.split(":", 1)
            parts = rest.split()
            if not parts:
                continue
            try:
                raw = int(parts[0])
            except ValueError:
                continue
            unit = parts[1].lower() if len(parts) > 1 else "kb"
            if unit == "kb":
                raw *= 1024
            elif unit == "mb":
                raw *= 1024 * 1024
            name = key.strip()
            if name == "MemTotal":
                total = raw
            elif name == "MemAvailable":
                avail = raw
        return total, avail

    @staticmethod
    def parse_macos_memsize(text: str) -> int | None:
        token = str(text or "").strip().split()[0] if str(text or "").strip() else ""
        if not token.isdigit():
            return None
        return int(token)

    @staticmethod
    def parse_windows_status(
        total: int | None, avail: int | None
    ) -> tuple[int | None, int | None]:
        t = int(total) if isinstance(total, int) and total >= 0 else None
        a = int(avail) if isinstance(avail, int) and avail >= 0 else None
        return t, a

    @staticmethod
    def _read_linux(path: Path = LINUX_MEMINFO) -> tuple[int | None, int | None]:
        try:
            return HostRam.parse_linux_meminfo(path.read_text(encoding="utf-8"))
        except OSError:
            return None, None

    @staticmethod
    def _read_macos() -> tuple[int | None, int | None]:
        try:
            proc = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, None
        return HostRam.parse_macos_memsize(proc.stdout), None

    @staticmethod
    def _read_windows() -> tuple[int | None, int | None]:
        try:
            import ctypes
        except ImportError:
            return None, None

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32),
                ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        except AttributeError:
            return None, None
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None, None
        return HostRam.parse_windows_status(status.ullTotalPhys, status.ullAvailPhys)

    @staticmethod
    def measure(
        *,
        system: str | None = None,
        meminfo_text: str | None = None,
        memsize_text: str | None = None,
        win_total: int | None = None,
        win_avail: int | None = None,
    ) -> dict[str, Any]:
        """Return ram_total_bytes/avail + gb + suggested band.

        Production reads the live host. Tests pass fixtures. Unknown stays
        omitted — never invent GB.
        """
        name = system if system is not None else platform.system()
        total: int | None = None
        avail: int | None = None
        if meminfo_text is not None:
            total, avail = HostRam.parse_linux_meminfo(meminfo_text)
        elif memsize_text is not None:
            total = HostRam.parse_macos_memsize(memsize_text)
        elif win_total is not None or win_avail is not None:
            total, avail = HostRam.parse_windows_status(win_total, win_avail)
        elif name == "Linux":
            total, avail = HostRam._read_linux()
        elif name == "Darwin":
            total, avail = HostRam._read_macos()
        elif name == "Windows":
            total, avail = HostRam._read_windows()
        total_gb = HostRam.bytes_to_gb(total)
        avail_gb = HostRam.bytes_to_gb(avail)
        return {
            "system": name,
            "ram_total_bytes": total,
            "ram_avail_bytes": avail,
            "ram_total_gb": total_gb,
            "ram_avail_gb": avail_gb,
            "suggested_band": HostRam.suggest_band(total_gb),
        }

    @staticmethod
    def low_avail_note(doc: dict[str, Any]) -> str | None:
        avail = doc.get("ram_avail_gb")
        if not isinstance(avail, (int, float)) or avail >= LOW_AVAIL_GB:
            return None
        return (
            f"avail RAM {avail} GB critically low — large waves may page "
            "(WARN only; not a spawn refuse)"
        )

    @staticmethod
    def doctor_lines(doc: dict[str, Any] | None = None) -> list[str]:
        measured = doc if isinstance(doc, dict) else HostRam.measure()
        total = measured.get("ram_total_gb")
        avail = measured.get("ram_avail_gb")
        suggested = measured.get("suggested_band") or "-"
        total_s = f"{total}" if total is not None else "unknown"
        line = f"ram_total_gb {total_s}  suggested={suggested}  ({BUDGET_NOTE})"
        lines = [line]
        if avail is not None:
            lines.append(f"ram_avail_gb {avail}")
        low = HostRam.low_avail_note(measured)
        if low:
            lines.append(f"note          {low}")
        lines.append(f"note          {CLOUD_NOTE}")
        return lines

    @staticmethod
    def event_fields(doc: dict[str, Any] | None = None) -> dict[str, Any]:
        measured = doc if isinstance(doc, dict) else HostRam.measure()
        out: dict[str, Any] = {}
        if measured.get("ram_total_gb") is not None:
            out["ram_total_gb"] = measured["ram_total_gb"]
        if measured.get("ram_avail_gb") is not None:
            out["ram_avail_gb"] = measured["ram_avail_gb"]
        if measured.get("suggested_band"):
            out["suggested_band"] = measured["suggested_band"]
        return out


class AgentBand:
    """Once-per-field wave-budget + multi-model consent. Not a supervisor."""

    BANDS = BANDS

    @staticmethod
    def normalize_band(raw: str, *, flag: str = "--agent-band") -> str:
        value = str(raw or "").strip()
        if value in ("-", "off", "none", ""):
            die(f"{flag} must be {'|'.join(BANDS)} (not off; omit to leave unset)")
        folded = re.sub(r"\s+", "", value)
        band = BAND_ALIASES.get(folded)
        if band is None:
            die(f"{flag} must be {'|'.join(BANDS)}; got {raw!r}")
        return band

    @staticmethod
    def normalize_multi(raw: str, *, flag: str = "--multi-model") -> bool:
        value = str(raw or "").strip().lower()
        if value in YES:
            return True
        if value in NO:
            return False
        die(f"{flag} must be yes or no; got {raw!r}")
        return False

    @staticmethod
    def of(order: dict[str, Any] | None) -> dict[str, Any] | None:
        raw = (order or {}).get("agent_band")
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def apply(
        order: dict[str, Any],
        band: str | None = None,
        multi_model: str | bool | None = None,
    ) -> bool:
        has_band = band is not None
        has_multi = multi_model is not None
        if not (has_band or has_multi):
            return False
        existing = AgentBand.of(order) or {}
        cfg: dict[str, Any] = dict(existing)
        if has_band:
            cfg["band"] = AgentBand.normalize_band(str(band))
        if has_multi:
            if isinstance(multi_model, bool):
                cfg["multi_model"] = multi_model
            else:
                cfg["multi_model"] = AgentBand.normalize_multi(str(multi_model))
        if cfg == existing:
            return False
        order["agent_band"] = cfg
        return True

    @staticmethod
    def format_line(cfg: Any) -> str:
        if not isinstance(cfg, dict) or not cfg:
            return ""
        parts: list[str] = []
        band = str(cfg.get("band") or "").strip()
        if band:
            parts.append(band)
        if "multi_model" in cfg:
            parts.append("multi-model=" + ("yes" if cfg.get("multi_model") else "no"))
        return " ".join(parts)

    @staticmethod
    def stamp_effort(hints: dict[str, str] | None) -> dict[str, str] | None:
        """Children default medium. High stays ORDER-authoring (#279), not slices."""
        from of_adapters import AdapterHints

        if not isinstance(hints, dict) or not hints:
            return hints
        out = dict(hints)
        raw = str(out.get("effort") or "").strip()
        if raw and raw not in AdapterHints.EFFORTS:
            die(
                f"pack --effort must be low|medium|high (got {raw!r}); "
                "children default medium"
            )
        if not raw:
            out["effort"] = AdapterHints.DEFAULT_EFFORT
        return out

    @staticmethod
    def pack_note(order: dict[str, Any], packed_count: int) -> str | None:
        """Advisory wave-size bias. Never refuse. Never a spawn cap."""
        cfg = AgentBand.of(order)
        if not cfg:
            return None
        band = str(cfg.get("band") or "").strip()
        if not band:
            return None
        hi = {"1-4": 4, "5-10": 10, "10-50": 50}.get(band)
        extra = ""
        if hi is not None and packed_count > hi:
            extra = (
                f"; {packed_count} packed exceeds {band} "
                f"({BUDGET_NOTE}; do not treat as refuse)"
            )
        multi = ""
        if "multi_model" in cfg:
            multi = (
                "; multi-model yes (task+adapters are the ceiling)"
                if cfg.get("multi_model")
                else "; multi-model no (stay same-model unless the human changes it)"
            )
        return f"agent_band={band} ({BUDGET_NOTE}){multi}{extra}"

    @staticmethod
    def add_flags(parser: Any) -> None:
        parser.add_argument(
            "--agent-band",
            dest="agent_band",
            choices=list(BANDS),
            help="wave budget 1-4|5-10|10-50 (not a spawn cap); store once",
        )
        parser.add_argument(
            "--multi-model",
            dest="multi_model",
            choices=["yes", "no"],
            help="optional multi-model/multi-quality; task+adapters are the ceiling",
        )

    @staticmethod
    def apply_args(order: dict[str, Any], args: Any) -> bool:
        return AgentBand.apply(
            order,
            band=getattr(args, "agent_band", None),
            multi_model=getattr(args, "multi_model", None),
        )

    @staticmethod
    def speak_init(doc: dict[str, Any] | None = None) -> list[str]:
        measured = doc if isinstance(doc, dict) else HostRam.measure()
        lines = ["host"]
        for line in HostRam.doctor_lines(measured):
            lines.append(f"  {line}")
        lines.append(
            "  next          ask once, then of patch --agent-band / --multi-model "
            "(do not re-ask each wave)"
        )
        return lines
