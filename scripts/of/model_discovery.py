"""Live harness model metadata; no inference, routing, or price lookup."""
from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone

from of_adapters import ADAPTER_BINS, ADAPTER_ORDER


class DiscoveryError(Exception):
    """A safe diagnostic code, never raw provider output."""


class Probe:
    """One bounded subprocess, including protocol reads and final cleanup."""

    def __init__(self, argv: list[str], timeout: float):
        self.deadline = time.monotonic() + timeout
        self.events: queue.Queue = queue.Queue()
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=os.name == "posix",
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        total = 0
        try:
            while True:
                line = self.proc.stdout.readline(1024 * 1024 + 1)
                total += len(line)
                if len(line) > 1024 * 1024 or total > 8 * 1024 * 1024:
                    self.events.put(DiscoveryError("output_limit"))
                    return
                if not line:
                    self.events.put(None)
                    return
                self.events.put(line)
        except (OSError, ValueError):
            self.events.put(DiscoveryError("process_io_error"))

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise DiscoveryError("timeout")
        return left

    def line(self) -> str | None:
        try:
            event = self.events.get(timeout=self.remaining())
        except queue.Empty:
            raise DiscoveryError("timeout") from None
        if isinstance(event, Exception):
            raise event
        return event.decode("utf-8", "replace") if event is not None else None

    def send(self, message: dict) -> None:
        self.remaining()
        try:
            self.proc.stdin.write((json.dumps(message) + "\n").encode())
            self.proc.stdin.flush()
        except (OSError, ValueError):
            raise DiscoveryError("process_io_error") from None

    def response(self, matches) -> dict:
        while True:
            line = self.line()
            if line is None:
                raise DiscoveryError("unexpected_eof")
            try:
                message = json.loads(line)
            except ValueError:
                raise DiscoveryError("invalid_json") from None
            if not isinstance(message, dict):
                raise DiscoveryError("invalid_response")
            if matches(message):
                return message

    def text(self) -> str:
        lines = []
        while (line := self.line()) is not None:
            lines.append(line)
        try:
            code = self.proc.wait(timeout=self.remaining())
        except subprocess.TimeoutExpired:
            raise DiscoveryError("timeout") from None
        if code:
            raise DiscoveryError("command_failed")
        return "".join(lines)

    def close(self) -> None:
        # Kill the group even when its parent exited but a descendant holds pipes.
        for sig in (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)):
            try:
                if os.name == "posix":
                    os.killpg(self.proc.pid, sig)
                elif self.proc.poll() is None:
                    self.proc.terminate() if sig == signal.SIGTERM else self.proc.kill()
            except ProcessLookupError:
                pass
            except PermissionError:
                # Some host sandboxes allow signalling the child but not its group.
                if self.proc.poll() is None:
                    self.proc.terminate() if sig == signal.SIGTERM else self.proc.kill()
            try:
                self.proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                continue
            if os.name != "posix":
                break
        self.reader.join(timeout=0.2)
        self.proc.stdin.close()
        self.proc.stdout.close()


def _string(value) -> str | None:
    return value if isinstance(value, str) and value else None


def _models(items, adapter: str) -> list[dict]:
    if not isinstance(items, list):
        raise DiscoveryError("invalid_models")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise DiscoveryError("invalid_model")
        model_id = _string(item.get("value" if adapter == "claude" else "id"))
        if not model_id:
            raise DiscoveryError("invalid_model_id")
        if adapter == "codex" and item.get("hidden") is True:
            continue
        efforts = item.get("supportedEffortLevels" if adapter == "claude"
                           else "supportedReasoningEfforts", [])
        if not isinstance(efforts, list):
            raise DiscoveryError("invalid_efforts")
        normalized = []
        for effort in efforts:
            if isinstance(effort, str):
                normalized.append({"effort": effort, "description": None})
            elif isinstance(effort, dict) and _string(effort.get("reasoningEffort")):
                normalized.append({"effort": effort["reasoningEffort"],
                                   "description": _string(effort.get("description"))})
            else:
                raise DiscoveryError("invalid_efforts")
        rows.append({
            "model_id": model_id,
            "resolved_model": _string(item.get("resolvedModel" if adapter == "claude" else "model")),
            "display_name": _string(item.get("displayName")),
            "description": _string(item.get("description")),
            "is_default": item.get("isDefault") if isinstance(item.get("isDefault"), bool) else None,
            "recommendation": _string(item.get("upgrade")) if adapter == "codex" else None,
            "default_effort": _string(item.get("defaultReasoningEffort")),
            "efforts": normalized,
            "price_public": "unknown",
        })
    return rows


def _codex(probe: Probe) -> list[dict]:
    probe.send({"id": 1, "method": "initialize", "params": {
        "clientInfo": {"name": "orderfield_models", "version": "1"},
        "capabilities": {},
    }})
    first = probe.response(lambda m: m.get("id") == 1)
    if "error" in first:
        raise DiscoveryError("initialize_failed")
    if not isinstance(first.get("result"), dict):
        raise DiscoveryError("invalid_initialize")
    probe.send({"method": "initialized", "params": {}})
    rows, cursors = [], set()
    cursor = None
    request_id = 2
    while True:
        probe.send({"id": request_id, "method": "model/list", "params": {
            "limit": 100, "includeHidden": False, "cursor": cursor,
        }})
        reply = probe.response(lambda m: m.get("id") == request_id)
        if "error" in reply:
            raise DiscoveryError("model_list_failed")
        result = reply.get("result")
        if not isinstance(result, dict):
            raise DiscoveryError("invalid_response")
        rows.extend(_models(result.get("data"), "codex"))
        cursor = result.get("nextCursor")
        if cursor is None:
            return rows
        if not _string(cursor) or cursor in cursors:
            raise DiscoveryError("invalid_pagination")
        cursors.add(cursor)
        request_id += 1


def _claude(probe: Probe) -> list[dict]:
    probe.send({"type": "control_request", "request_id": "models", "request": {"subtype": "initialize"}})
    reply = probe.response(lambda m: m.get("type") == "control_response"
                           and isinstance(m.get("response"), dict)
                           and m["response"].get("request_id") == "models")
    response = reply["response"]
    if response.get("subtype") != "success":
        raise DiscoveryError("initialize_failed")
    payload = response.get("response")
    if not isinstance(payload, dict):
        raise DiscoveryError("invalid_response")
    return _models(payload.get("models"), "claude")


def _listed(text: str, adapter: str) -> list[dict]:
    # Parse only documented list rows, discarding banners/account information.
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    items = []
    default = re.search(r"(?m)^Default model:\s*(\S+)\s*$", text)
    in_list = False
    for line in text.splitlines():
        if adapter == "agy":
            match = re.fullmatch(r"([\w./:-]+)\t([^\t]+)", line)
            if match:
                items.append({"id": match[1], "displayName": match[2]})
            continue
        if line.strip() in {"Available models", "Available models:"}:
            in_list = True
            continue
        if not in_list:
            continue
        if line.strip().startswith("Tip:"):
            break
        if adapter == "grok":
            match = re.fullmatch(r"\s+[*-]\s+([\w./:-]+)(?:\s+\(default\))?\s*", line)
        else:
            match = re.fullmatch(r"\s*([\w./:-]+)(?:\s+-\s+(.+?))?(?:\s+\((current|default|current, default)\))?\s*", line)
        if not match:
            continue
        model_id = match[1]
        items.append({"id": model_id, "displayName": match[2] if adapter == "cursor" else None,
                      "isDefault": model_id == default[1] if default else
                      (True if adapter == "grok" and "(default)" in line else
                       ("default" in (match[3] or "")) if adapter == "cursor" else None)})
    return _models(items, adapter)


def discover(adapter: str, timeout: float = 15) -> dict:
    source = {"codex": "codex app-server: initialize → model/list",
              "claude": "claude stream-json: control_request initialize response.models",
              "grok": "grok models", "cursor": "agent models / cursor-agent models",
              "agy": "agy models"}.get(adapter)
    report = {"adapter": adapter, "source": source, "checked_at": None,
              "status": "unsupported", "error": "unsupported", "models": []}
    probe = None
    try:
        if source is None:
            return report
        binary = next((path for name in ADAPTER_BINS[adapter]
                       if (path := shutil.which(name))), None)
        if not binary:
            report.update(status="missing", error="missing_binary")
            return report
        if adapter == "codex":
            argv = [binary, "app-server"]
        elif adapter == "claude":
            argv = [binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                    "--verbose", "--tools", "", "--strict-mcp-config", "--mcp-config",
                    '{"mcpServers":{}}', "--setting-sources", ""]
        else:
            argv = [binary, "models"]
        probe = Probe(argv, timeout)
        rows = (_codex(probe) if adapter == "codex" else _claude(probe)
                if adapter == "claude" else _listed(probe.text(), adapter))
        if not rows:
            raise DiscoveryError("empty_models")
        report.update(status="ok", error=None, models=rows)
    except DiscoveryError as exc:
        report.update(status="error", error=str(exc))
    except OSError:
        report.update(status="error", error="process_io_error")
    finally:
        if probe is not None:
            probe.close()
        report["checked_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return report


def cmd_models(args) -> None:
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 120:
        raise ValueError("--timeout must be finite, > 0 and <= 120 seconds")
    reports = [discover(name, args.timeout) for name in ([args.adapter] if args.adapter else ADAPTER_ORDER)]
    if args.json:
        print(json.dumps({"v": 1, "kind": "model_discovery", "adapters": reports}, ensure_ascii=False))
    else:
        for report in reports:
            print(f"{report['adapter']}: {report['status']} checked_at={report['checked_at']} source={report['source']}")
            if report["error"]:
                print(f"  error: {report['error']}")
            for row in report["models"]:
                print(f"  {row['model_id']} resolved={row['resolved_model']} default={row['is_default']} price=unknown")
                print(f"    {row['display_name']} — {row['description']}")
                print(f"    efforts={row['efforts']} default_effort={row['default_effort']} recommendation={row['recommendation']}")
    # All-adapter inventory includes unsupported adapters normally; selected failure is nonzero.
    failed = any(r["status"] == "error" for r in reports)
    if failed or (args.adapter and reports[0]["status"] != "ok"):
        raise SystemExit(2)
