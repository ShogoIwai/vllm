#!/usr/bin/env python3
"""
UserPromptSubmit hook: quota-aware Qwen delegation. (T2)

Reads the 5h-quota status written by proxy.py (~/.claude/usage-status.json).
When the unified 5h utilization is at/above the threshold, injects an
additionalContext instruction telling Claude to prefer the local Qwen model
(qwen-local MCP: ask_qwen / ask_qwen_code) for code generation, debugging,
and refactoring. Below the threshold it emits nothing (normal operation).

The decision logic lives in the shared ``quota_route`` helper so the Codex
emitter (``codex_quota_context.py``) stays in sync. See ``quota_route`` for the
full list of configuration environment variables.

This hook is read-only and never blocks the prompt: any error results in a
clean no-op so a stale/missing/corrupt status file cannot wedge the session.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_route


def main() -> int:
    # Drain stdin (hook receives the prompt event as JSON) but we don't need it.
    try:
        sys.stdin.read()
    except Exception:
        pass

    try:
        cfg = quota_route.read_env()
        status = quota_route.load_status(cfg["status_path"])
        util = quota_route.anthropic_utilization(status, cfg["max_age"])
    except Exception:
        return 0

    if util is None or util < cfg["threshold"]:
        return 0  # no/insufficient signal -> inject nothing

    context = quota_route.build_guard_text(util, cfg["threshold"], cfg["tools"])
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
