# Route Claude Code through the monitoring proxy (proxy.py on :8000 -> Anthropic)
# so the 5h-quota rate-limit headers get captured into ~/.claude/usage-status.json.
setenv ANTHROPIC_BASE_URL http://localhost:8000
