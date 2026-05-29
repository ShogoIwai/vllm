# vLLM (local Qwen) now listens on :8001; :8000 is the monitoring proxy.
setenv OPENAI_BASE_URL http://localhost:8001/v1
setenv OPENAI_API_KEY dummy

# Route Claude Code through the monitoring proxy (proxy.py on :8000 -> Anthropic)
# so the 5h-quota rate-limit headers get captured into ~/.claude/usage-status.json.
setenv ANTHROPIC_BASE_URL http://localhost:8000

# Configure sgpt to use local vLLM server
if ( -f ~/.config/shell_gpt/.sgptrc ) then
    sed -i 's|^API_BASE_URL=.*|API_BASE_URL=http://localhost:8001/v1|' ~/.config/shell_gpt/.sgptrc
    sed -i 's|^DEFAULT_MODEL=.*|DEFAULT_MODEL=local-model-qwen3-coder-30b-a3b-awq|' ~/.config/shell_gpt/.sgptrc
endif
