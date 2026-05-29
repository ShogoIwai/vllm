#!/usr/bin/env python3
"""
UserPromptSubmit hook: quota-aware Qwen delegation. (T2)

Reads the 5h-quota status written by proxy.py (~/.claude/usage-status.json).
When the unified 5h utilization is at/above the threshold, injects an
additionalContext instruction telling Claude to prefer the local Qwen model
(qwen-local MCP: ask_qwen / ask_qwen_code) for code generation, debugging,
and refactoring. Below the threshold it emits nothing (normal operation).

Configuration (all optional, via environment):
  USAGE_STATUS_PATH    status file path (default ~/.claude/usage-status.json)
  QWEN_ROUTE_THRESHOLD 5h utilization trigger, 0.0-1.0 (default 0.85)
  QWEN_ROUTE_TOOLS     comma-separated MCP tool names to recommend
                       (default "ask_qwen, ask_qwen_code")
  QWEN_ROUTE_MAX_AGE   max status-file age in seconds before it is ignored
                       as stale (default 21600 = 6h; 0 disables the check)

This hook is read-only and never blocks the prompt: any error results in a
clean no-op so a stale/missing/corrupt status file cannot wedge the session.
"""
import json
import os
import sys
import time


def main() -> int:
    # Drain stdin (hook receives the prompt event as JSON) but we don't need it.
    try:
        sys.stdin.read()
    except Exception:
        pass

    status_path = os.environ.get(
        "USAGE_STATUS_PATH", os.path.expanduser("~/.claude/usage-status.json")
    )
    try:
        threshold = float(os.environ.get("QWEN_ROUTE_THRESHOLD", "0.85"))
    except ValueError:
        threshold = 0.85
    try:
        max_age = int(os.environ.get("QWEN_ROUTE_MAX_AGE", "21600"))
    except ValueError:
        max_age = 21600
    tools = os.environ.get("QWEN_ROUTE_TOOLS", "ask_qwen, ask_qwen_code").strip()

    try:
        with open(status_path) as f:
            status = json.load(f)
    except Exception:
        return 0  # no status yet -> normal operation

    util = status.get("utilization_5h")
    if not isinstance(util, (int, float)):
        return 0

    # Ignore stale data (proxy not in the path / Claude Code not routed).
    if max_age > 0:
        fetched_at = status.get("fetched_at")
        if isinstance(fetched_at, (int, float)) and (time.time() - fetched_at) > max_age:
            return 0

    if util < threshold:
        return 0  # plenty of quota left -> inject nothing

    pct = round(util * 100)
    context = (
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

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
