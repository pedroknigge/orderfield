"""Read operating-system process identity and activity for field provenance."""
from __future__ import annotations

import errno
import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

_DARWIN_CTL_KERN = 1
_DARWIN_KERN_PROCARGS2 = 49


def _nul_env_map(data: bytes) -> dict[str, str]:
    env: dict[str, str] = {}
    for entry in data.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, _, value = entry.partition(b"=")
        try:
            env[key.decode("utf-8")] = value.decode("utf-8", "replace")
        except UnicodeDecodeError:
            continue
    return env


def _linux_exec_environ(pid: int) -> dict[str, str] | None:
    path = Path(f"/proc/{int(pid)}/environ")
    if not path.is_file():
        return None
    try:
        return _nul_env_map(path.read_bytes())
    except OSError:
        return None


def _darwin_exec_environ(pid: int) -> dict[str, str] | None:
    """KERN_PROCARGS2 env block at exec (not ps -E command-line text)."""
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return None
    libname = ctypes.util.find_library("c")
    if not libname:
        return None
    try:
        libc = ctypes.CDLL(libname, use_errno=True)
    except OSError:
        return None
    libc.sysctl.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    libc.sysctl.restype = ctypes.c_int
    mib = (ctypes.c_int * 3)(_DARWIN_CTL_KERN, _DARWIN_KERN_PROCARGS2, int(pid))
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value < 4:
        return None
    raw = b""
    for _ in range(3):
        buf = ctypes.create_string_buffer(size.value + 256)
        got = ctypes.c_size_t(len(buf))
        if libc.sysctl(mib, 3, buf, ctypes.byref(got), None, 0) == 0:
            raw = buf.raw[: got.value]
            break
        if ctypes.get_errno() != errno.ENOMEM:
            return None
        size = ctypes.c_size_t(max(size.value * 2, len(buf) * 2))
    else:
        return None
    if len(raw) < 4:
        return None
    argc = int.from_bytes(raw[:4], sys.byteorder, signed=True)
    if argc < 0 or argc > 4096:
        return None
    rest = raw[4:]
    path_end = rest.find(b"\0")
    if path_end < 0:
        return None
    i = path_end + 1
    while i < len(rest) and rest[i] == 0:
        i += 1
    parts = rest[i:].split(b"\0")
    if len(parts) < argc:
        return None
    env_blob = b"\0".join(parts[argc:])
    return _nul_env_map(env_blob)


def _proc_exec_environ(pid: int) -> dict[str, str] | None:
    """Environment at exec. Live os.environ can drop OF_CHILD (env -u)."""
    if pid <= 1:
        return None
    linux = _linux_exec_environ(pid)
    if linux is not None:
        return linux
    if sys.platform == "darwin":
        return _darwin_exec_environ(pid)
    return None


def _proc_stat_fields(pid: int) -> list[str] | None:
    stat = Path(f"/proc/{int(pid)}/stat")
    if not stat.is_file():
        return None
    try:
        text = stat.read_text(encoding="utf-8", errors="replace")
        return text[text.rfind(")") + 1 :].split()
    except OSError:
        return None


def _proc_ppid(pid: int) -> int:
    fields = _proc_stat_fields(pid)
    if fields is not None:
        try:
            return int(fields[1])
        except (IndexError, ValueError):
            return 0
    try:
        proc = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "ppid="],
            capture_output=True,
            text=True,
            timeout=1,
        )
        return int(proc.stdout.strip().split()[-1])
    except (OSError, IndexError, ValueError, subprocess.TimeoutExpired):
        return 0


def _proc_lstart(pid: int) -> str | None:
    """``ps -o lstart=`` under LC_ALL=C TZ=UTC: the same text in any harness."""
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    try:
        proc = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=1,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return " ".join(proc.stdout.split()) or None


def _proc_starttime(pid: int) -> str | None:
    """Process starttime token. Survives exec; pid reuse without it is not a match.

    Linux: /proc stat ticks. Elsewhere: lstart in C locale and UTC, so two
    harnesses with a different TZ or LANG read the same string.
    """
    fields = _proc_stat_fields(pid)
    if fields is not None:
        try:
            return str(fields[19])
        except IndexError:
            return None
    return _proc_lstart(pid)


_LSTART_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def parse_lstart(text: Any, *, utc: bool) -> int | None:
    """Epoch of a C-locale ``Thu Oct  8 11:28:27 2026``; None for other locales.

    utc=False reads a v0.8.34 record (local time of whoever wrote it).
    """
    parts = str(text or "").split()
    if len(parts) != 5 or parts[1] not in _LSTART_MONTHS:
        return None
    try:
        hh, mm, ss = (int(x) for x in parts[3].split(":"))
        fields = (int(parts[4]), _LSTART_MONTHS.index(parts[1]) + 1, int(parts[2]), hh, mm, ss)
        if utc:
            return int(datetime(*fields, tzinfo=timezone.utc).timestamp())
        return int(time.mktime((*fields, 0, 0, -1)))
    except (ValueError, OverflowError):
        return None


@lru_cache(maxsize=1)
def _boot_epoch() -> int | None:
    try:
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def proc_start_epoch(pid: int) -> int | None:
    """Process start as a UTC epoch second. TZ/locale-free on every host."""
    fields = _proc_stat_fields(pid)
    boot = _boot_epoch()
    if fields is not None and boot is not None:
        try:
            return boot + int(fields[19]) // int(os.sysconf("SC_CLK_TCK"))
        except (IndexError, ValueError, OSError):
            return None
    return parse_lstart(_proc_lstart(pid), utc=True)


@lru_cache(maxsize=1)
def host_id() -> str:
    """Stable id of this machine's pid namespace. A pid means nothing elsewhere."""
    import socket

    seed = socket.gethostname()
    try:
        seed += "|" + Path("/etc/machine-id").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def proc_pcpu(pid: int) -> str | None:
    """One ``ps`` %CPU sample. Not a supervisor; not a load average."""
    try:
        pid_n = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_n <= 1:
        return None
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid_n), "-o", "pcpu="],
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        return f"{float(raw)}%"
    except ValueError:
        return None


def _proc_sid(pid: int) -> int:
    if not hasattr(os, "getsid"):
        return 0
    try:
        return int(os.getsid(int(pid)))
    except OSError:
        return 0
