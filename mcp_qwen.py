#!/usr/bin/env python3
"""MCP server: exposes local Qwen (vLLM :8000) as Claude Code tools."""

import json
import os
import time
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from openai import OpenAI

VLLM_BASE_URL = "http://localhost:8000/v1"
MODEL_ID = "local-model-qwen3-coder-30b-a3b-awq"

# T6: lightweight token-usage instrumentation. Append one JSON object per call.
USAGE_LOG = os.environ.get(
    "QWEN_USAGE_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.log")
)

mcp = FastMCP("qwen-local")
client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy")


def _log_usage(tool: str, system: str, user: str, resp, latency_s: float) -> None:
    """Append a JSONL usage record. Never raise into the caller."""
    try:
        usage = getattr(resp, "usage", None)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "model": MODEL_ID,
            "input_chars": len(system) + len(user),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "latency_s": round(latency_s, 3),
        }
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _chat(system: str, user: str, max_tokens: int = 2048, tool: str = "_chat") -> str:
    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    _log_usage(tool, system, user, resp, time.monotonic() - t0)
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
    return _chat("You are a helpful coding assistant.", prompt, tool="ask_qwen")


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
    return _chat(system, prompt, tool="ask_qwen_code")


if __name__ == "__main__":
    mcp.run(transport="stdio")
