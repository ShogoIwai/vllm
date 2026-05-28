setenv OPENAI_BASE_URL http://localhost:8000/v1
setenv OPENAI_API_KEY dummy

# Configure sgpt to use local vLLM server
if ( -f ~/.config/shell_gpt/.sgptrc ) then
    sed -i 's|^API_BASE_URL=.*|API_BASE_URL=http://localhost:8000/v1|' ~/.config/shell_gpt/.sgptrc
    sed -i 's|^DEFAULT_MODEL=.*|DEFAULT_MODEL=local-model-qwen3-coder-30b-a3b-awq|' ~/.config/shell_gpt/.sgptrc
endif
