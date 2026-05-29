#!/usr/bin/env python3
"""
Transparent monitoring proxy between Claude Code and Anthropic.

Monitors the Anthropic unified 5h-quota rate-limit headers on upstream
responses and writes the latest values to ~/.claude/usage-status.json, so
downstream tooling (e.g. a UserPromptSubmit hook) can route work to the local
Qwen model when the 5h quota runs low. (T1)

The proxy forwards requests/responses verbatim; the header monitor is
non-invasive and only writes the status file when the upstream response
actually carries the anthropic-ratelimit-* headers. Point BACKEND at the
Anthropic API (the default) and export ANTHROPIC_BASE_URL=https://api.anthropic.com
in the Claude Code environment to route through it.
"""
import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

BACKEND = os.environ.get("PROXY_BACKEND", "https://api.anthropic.com")

# Where to persist the latest observed 5h-quota utilization.
USAGE_STATUS_PATH = Path(
    os.environ.get(
        "USAGE_STATUS_PATH",
        os.path.expanduser("~/.claude/usage-status.json"),
    )
)

# Anthropic unified rate-limit headers we passively track. The numeric ones
# are coerced to float/int; everything else is stored as-is.
_RATELIMIT_HEADERS = {
    "anthropic-ratelimit-unified-5h-utilization": ("utilization_5h", float),
    "anthropic-ratelimit-unified-5h-remaining": ("remaining_5h", int),
    "anthropic-ratelimit-unified-5h-reset": ("reset_5h", int),
    "anthropic-ratelimit-unified-7d-utilization": ("utilization_7d", float),
}


def _write_usage_status(headers) -> None:
    """Extract the unified rate-limit headers (if any) and persist them.

    Writes atomically so a concurrent reader never sees a half-written file.
    Silently no-ops when none of the tracked headers are present.
    """
    parsed = {}
    for header, (key, caster) in _RATELIMIT_HEADERS.items():
        raw = headers.get(header)
        if raw is None:
            continue
        try:
            parsed[key] = caster(raw)
        except (TypeError, ValueError):
            parsed[key] = raw

    if not parsed:
        return

    parsed["fetched_at"] = int(time.time())

    try:
        USAGE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(USAGE_STATUS_PATH.parent),
            prefix=".usage-status-",
            suffix=".tmp",
        )
        with os.fdopen(fd, "w") as f:
            json.dump(parsed, f)
        os.replace(tmp, USAGE_STATUS_PATH)
        if "utilization_5h" in parsed:
            print(f"[proxy] 5h utilization={parsed['utilization_5h']}")
    except Exception as exc:  # never let monitoring break the proxy path
        print(f"[proxy] failed to write usage status: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=300)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


async def _stream(response: httpx.Response):
    # aiter_raw yields the original (possibly compressed) bytes untouched, so
    # we stay a transparent proxy: the content-encoding/content-length headers
    # we forward stay consistent with the body. (aiter_bytes would silently
    # decompress while we still forward content-encoding -> client ZlibError.)
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() != "host"}

    req = request.app.state.client.build_request(
        method=request.method,
        url=f"{BACKEND}/{path}",
        headers=headers,
        content=body,
        params=dict(request.query_params),
    )
    response = await request.app.state.client.send(req, stream=True)

    _write_usage_status(response.headers)

    return StreamingResponse(
        _stream(response),
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.headers.get("content-type"),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
