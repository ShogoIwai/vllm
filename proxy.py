#!/usr/bin/env python3
"""
Proxy between Claude Code and vLLM.
Caps max_tokens to prevent context overflow.
"""
import json
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

BACKEND = "http://localhost:8000"
MAX_TOKENS_CAP = 129024  # adjust as needed


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=300)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


async def _stream(response: httpx.Response):
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    finally:
        await response.aclose()


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}

    if request.method == "POST" and body:
        try:
            data = json.loads(body)
            if isinstance(data.get("max_tokens"), int) and data["max_tokens"] > MAX_TOKENS_CAP:
                print(f"[proxy] cap max_tokens {data['max_tokens']} -> {MAX_TOKENS_CAP}")
                data["max_tokens"] = MAX_TOKENS_CAP
            body = json.dumps(data).encode()
        except Exception:
            pass

    headers["content-length"] = str(len(body))

    req = request.app.state.client.build_request(
        method=request.method,
        url=f"{BACKEND}/{path}",
        headers=headers,
        content=body,
        params=dict(request.query_params),
    )
    response = await request.app.state.client.send(req, stream=True)

    return StreamingResponse(
        _stream(response),
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.headers.get("content-type"),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
