#!/usr/bin/env python3
"""
Codex launch-boundary quota context emitter.

Codex has no UserPromptSubmit-style hook, so quota state cannot be injected per
prompt the way Claude Code does. Instead this script is meant to be run at the
Codex launch boundary (CLI wrapper or plugin prompt assembly); its stdout is
prepended/appended to the Codex prompt.

It reads two quota signals via the shared ``quota_route`` helper:

  * Anthropic 5h quota  -- from ~/.claude/usage-status.json (written by proxy.py)
  * Codex/OpenAI 5h quota -- from the newest ~/.codex/sessions rollout JSONL
    (rate_limits.primary.used_percent), normalized to 0.0-1.0

If EITHER signal is at/above its threshold, it prints a single plain-text quota
guard block. Below threshold (or with no usable signal) it prints nothing.

Fail-closed: missing, stale, or corrupt inputs never raise and never block
prompt assembly -- the script always exits 0.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_route


def main() -> int:
    try:
        cfg = quota_route.read_env()

        # Anthropic signal (0.0-1.0) vs QWEN_ROUTE_THRESHOLD.
        status = quota_route.load_status(cfg["status_path"])
        anthropic = quota_route.anthropic_utilization(status, cfg["max_age"])

        # Codex signal (0.0-1.0) vs CODEX_QWEN_ROUTE_THRESHOLD.
        codex = quota_route.load_codex_status(
            cfg["codex_sessions_dir"], cfg["max_age"]
        )

        over = []
        if anthropic is not None and anthropic >= cfg["threshold"]:
            over.append((anthropic, cfg["threshold"]))
        if codex is not None and codex >= cfg["codex_threshold"]:
            over.append((codex, cfg["codex_threshold"]))

        if not over:
            return 0  # plenty of quota on both signals -> emit nothing

        # Report against whichever signal is most over its threshold.
        util, threshold = max(over, key=lambda pair: pair[0] - pair[1])
        sys.stdout.write(
            quota_route.build_codex_guard_text(util, threshold, cfg["tools"])
        )
        sys.stdout.write("\n")
    except Exception:
        # Never block Codex prompt assembly on a monitoring failure.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
