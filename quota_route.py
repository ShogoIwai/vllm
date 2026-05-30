#!/usr/bin/env python3
"""
Shared quota-routing helper for the Qwen delegation tooling.

This module centralizes the logic that decides whether cloud quota is running
low enough that downstream tooling should bias work toward the local Qwen
model. It is consumed by two emitters:

  * ``usage_route_hook.py`` -- Claude Code ``UserPromptSubmit`` hook (emits the
    quota guard as ``hookSpecificOutput.additionalContext`` JSON).
  * ``codex_quota_context.py`` -- Codex launch-boundary emitter (emits the
    quota guard as plain text).

Two independent quota signals are supported:

  * Anthropic 5h quota -- captured by ``proxy.py`` into
    ``~/.claude/usage-status.json`` as ``utilization_5h`` (0.0-1.0).
  * Codex/OpenAI 5h quota -- read on demand from the newest Codex session
    rollout JSONL under ``~/.codex/sessions`` as
    ``rate_limits.primary.used_percent`` (0-100, normalized to 0.0-1.0 here).

Everything here is read-only and fail-closed: any missing, stale, or corrupt
input results in "no quota guard" rather than an error, so a bad status file
can never wedge a session.

Configuration (all optional, via environment):
  USAGE_STATUS_PATH          Anthropic status file path
                             (default ~/.claude/usage-status.json)
  QWEN_ROUTE_THRESHOLD       Anthropic 5h utilization trigger, 0.0-1.0
                             (default 0.85)
  CODEX_QWEN_ROUTE_THRESHOLD Codex 5h utilization trigger, 0.0-1.0
                             (default = QWEN_ROUTE_THRESHOLD)
  QWEN_ROUTE_TOOLS           comma-separated MCP tool names to recommend
                             (default "ask_qwen, ask_qwen_code")
  QWEN_ROUTE_MAX_AGE         max status-file age in seconds before it is
                             ignored as stale (default 21600 = 6h; 0 disables)
  CODEX_SESSIONS_DIR         Codex sessions root (default ~/.codex/sessions)
"""
import json
import os
import time
from pathlib import Path

DEFAULT_THRESHOLD = 0.85
DEFAULT_MAX_AGE = 21600  # 6h
DEFAULT_TOOLS = "ask_qwen, ask_qwen_code"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def read_env() -> dict:
    """Resolve all configuration from the environment, with safe defaults."""
    threshold = _env_float("QWEN_ROUTE_THRESHOLD", DEFAULT_THRESHOLD)
    codex_threshold = _env_float("CODEX_QWEN_ROUTE_THRESHOLD", threshold)
    return {
        "status_path": Path(
            os.environ.get(
                "USAGE_STATUS_PATH",
                os.path.expanduser("~/.claude/usage-status.json"),
            )
        ),
        "threshold": threshold,
        "codex_threshold": codex_threshold,
        "max_age": _env_int("QWEN_ROUTE_MAX_AGE", DEFAULT_MAX_AGE),
        "tools": os.environ.get("QWEN_ROUTE_TOOLS", DEFAULT_TOOLS).strip(),
        "codex_sessions_dir": Path(
            os.environ.get(
                "CODEX_SESSIONS_DIR",
                os.path.expanduser("~/.codex/sessions"),
            )
        ),
    }


# --------------------------------------------------------------------------
# Anthropic quota (status file written by proxy.py)
# --------------------------------------------------------------------------
def load_status(path) -> dict | None:
    """Load the Anthropic status JSON. Returns None if unreadable/corrupt."""
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def anthropic_utilization(status, max_age: int, now: float | None = None):
    """Return the Anthropic 5h utilization (0.0-1.0) or None.

    None is returned when the value is missing/non-numeric or the status is
    stale (older than ``max_age`` seconds; ``max_age <= 0`` disables the check).
    """
    if not isinstance(status, dict):
        return None
    util = status.get("utilization_5h")
    if not isinstance(util, (int, float)):
        return None
    if max_age > 0:
        fetched_at = status.get("fetched_at")
        if now is None:
            now = time.time()
        if isinstance(fetched_at, (int, float)) and (now - fetched_at) > max_age:
            return None
    return float(util)


# --------------------------------------------------------------------------
# Codex quota (newest session rollout JSONL under ~/.codex/sessions)
# --------------------------------------------------------------------------
def _newest_jsonl(sessions_dir: Path):
    try:
        files = [p for p in sessions_dir.rglob("rollout-*.jsonl") if p.is_file()]
    except Exception:
        return None
    if not files:
        return None
    try:
        return max(files, key=lambda p: p.stat().st_mtime)
    except Exception:
        return None


def _extract_used_percent(obj):
    """Best-effort pull of rate_limits.primary.used_percent from a JSON value."""
    if not isinstance(obj, dict):
        return None
    rl = obj.get("rate_limits")
    # rate_limits may sit at the top level or nested inside a payload/msg field.
    if rl is None:
        for key in ("payload", "msg", "message", "data"):
            nested = obj.get(key)
            if isinstance(nested, dict) and "rate_limits" in nested:
                rl = nested["rate_limits"]
                break
    if not isinstance(rl, dict):
        return None
    primary = rl.get("primary")
    if not isinstance(primary, dict):
        return None
    used = primary.get("used_percent")
    return float(used) if isinstance(used, (int, float)) else None


def load_codex_status(sessions_dir, max_age: int, now: float | None = None):
    """Return the Codex 5h utilization (0.0-1.0) from the newest JSONL, or None.

    Scans the newest rollout file from the end so the most recent
    ``rate_limits`` event wins. ``used_percent`` (0-100) is normalized to
    0.0-1.0 to match the Anthropic scale. Stale files (mtime older than
    ``max_age``) are ignored. Fail-closed: any error returns None.
    """
    sessions_dir = Path(sessions_dir)
    newest = _newest_jsonl(sessions_dir)
    if newest is None:
        return None
    if max_age > 0:
        if now is None:
            now = time.time()
        try:
            if (now - newest.stat().st_mtime) > max_age:
                return None
        except Exception:
            return None
    try:
        with open(newest) as f:
            lines = f.readlines()
    except Exception:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line or "rate_limits" not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        used = _extract_used_percent(obj)
        if used is not None:
            return used / 100.0
    return None


# --------------------------------------------------------------------------
# Guard text
# --------------------------------------------------------------------------
def build_guard_text(util: float, threshold: float, tools: str) -> str:
    """Build the quota guard instruction shared by both emitters."""
    pct = round(util * 100)
    return (
        f"[QUOTA GUARD] The Anthropic 5h usage quota is at {pct}% "
        f"(>= {round(threshold * 100)}% threshold). To conserve the remaining "
        f"cloud quota, you MUST now prefer the local Qwen model via the "
        f"qwen-local MCP server ({tools}) as the FIRST choice for any code "
        f"generation, debugging, refactoring, unit-test writing, or "
        f"self-contained explanation/summary/translation subtask. Only keep a "
        f"subtask in Claude when it genuinely requires cross-file reasoning, "
        f"root-cause analysis, tool/filesystem orchestration, or carries high "
        f"risk of silent bugs. Apply the existing task-shape delegation policy "
        f"(CLAUDE.md / AGENTS.md), now biased aggressively toward local "
        f"delegation."
    )


def build_codex_guard_text(util: float, threshold: float, tools: str) -> str:
    """Plain-text quota guard for Codex (no JSON wrapper, Codex-oriented wording)."""
    pct = round(util * 100)
    return (
        f"[QUOTA GUARD] Cloud quota is at {pct}% (>= {round(threshold * 100)}% "
        f"threshold). Prefer local Qwen via the qwen-local MCP server ({tools}) "
        f"as the FIRST choice for code generation, debugging, refactoring, test "
        f"writing, and self-contained explanation/summary/translation subtasks. "
        f"Codex still owns file I/O, command execution, edits, verification, and "
        f"final decisions. Do not force-offload cross-file reasoning, root-cause "
        f"analysis, architecture decisions, or high-risk review conclusions just "
        f"to save quota."
    )
