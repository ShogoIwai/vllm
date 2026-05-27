#!/usr/bin/env python3
"""MCP server: exposes local Qwen (vLLM :8000) as Claude Code tools."""

from mcp.server.fastmcp import FastMCP
from openai import OpenAI

VLLM_BASE_URL = "http://localhost:8000/v1"
MODEL_ID = "local-model-qwen2.5-coder-14b-awq"

mcp = FastMCP("qwen-local")
client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy")


def _chat(system: str, user: str, max_tokens: int = 2048) -> str:
    resp = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


@mcp.tool()
def ask_qwen(prompt: str) -> str:
    """Ask the local Qwen model a general question or request.

    Use this for lightweight tasks to save Claude API tokens:
    - Drafting boilerplate code or test cases
    - Explaining a short code snippet
    - Summarizing text
    - Translating comments or variable names
    - Answering simple factual questions about code patterns
    Do NOT use for tasks requiring file system access, tool use, or multi-step reasoning.
    """
    return _chat("You are a helpful coding assistant.", prompt)


@mcp.tool()
def ask_qwen_code(language: str, prompt: str) -> str:
    """Ask the local Qwen model to write or refactor code in a specific language.

    Use this for:
    - Generating boilerplate / stub implementations
    - Rewriting a function in a different style
    - Writing unit tests given a function signature
    - Translating code from one language to another
    Provide the target language and a clear description.
    """
    system = (
        f"You are an expert {language} programmer. "
        "Output only code unless asked for explanation. "
        "Use concise, idiomatic style."
    )
    return _chat(system, prompt)


if __name__ == "__main__":
    mcp.run(transport="stdio")
