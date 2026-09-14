from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ts_knowledge_agent.agent.runtime import create_provider, run_agent
from ts_knowledge_agent.agent.secrets import read_api_key, secret_path
from ts_knowledge_agent.agent.setup import mask_key
from ts_knowledge_agent.config import Settings

app = FastAPI(title="TS Knowledge Agent", version="0.1.0")


def config_path() -> Path:
    import os

    return Path(os.getenv("TS_KB_CONFIG", ".local/ts-kb.json")).expanduser()


def load_settings() -> Settings:
    path = config_path()
    if not path.is_file():
        raise HTTPException(status_code=503, detail=f"configuration file not found: {path}")
    return Settings.from_file(path)


class ChatRequest(BaseModel):
    question: str
    max_steps: int | None = None


class ConfigPayload(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    max_steps: int | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ts-team-knowledge-agent"}


@app.get("/api/v1/status")
def status() -> dict[str, str]:
    return {"status": "ready", "protocol": "sse", "prompt_version": "v1"}


@app.get("/api/v1/config")
def get_config() -> dict:
    settings = load_settings()
    return {
        "provider": settings.model_provider,
        "model": settings.model_name,
        "base_url": settings.model_base_url,
        "max_tokens": settings.model_max_tokens,
        "max_steps": settings.model_max_steps,
        "api_key": mask_key(read_api_key(settings.working_directory)),
        "api_key_path": str(secret_path(settings.working_directory)),
    }


@app.put("/api/v1/config")
def put_config(payload: ConfigPayload) -> dict:
    from dataclasses import replace

    settings = load_settings()
    updates: dict = {}
    if payload.provider is not None:
        updates["model_provider"] = payload.provider.strip()
    if payload.model is not None:
        updates["model_name"] = payload.model.strip()
    if payload.base_url is not None:
        updates["model_base_url"] = payload.base_url.strip()
    if payload.max_tokens is not None:
        updates["model_max_tokens"] = int(payload.max_tokens)
    if payload.max_steps is not None:
        updates["model_max_steps"] = int(payload.max_steps)
    if not updates:
        raise HTTPException(status_code=400, detail="no configuration fields provided")
    updated = replace(settings, **updates)
    updated.write_file(config_path())
    return get_config()


def _provider(settings: Settings):
    provider = create_provider(settings)
    if provider is None:
        raise HTTPException(status_code=503, detail="model provider is not configured; set provider, base url, model and api key")
    return provider


@app.post("/api/v1/chat")
def chat(request: ChatRequest) -> dict:
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    settings = load_settings()
    provider = _provider(settings)
    steps = request.max_steps or settings.model_max_steps
    result = run_agent(settings, question, provider, max_steps=steps)
    return {
        "answer": result.answer,
        "citations": result.citations,
        "steps": result.steps,
        "error": result.error,
    }


@app.post("/api/v1/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    settings = load_settings()
    provider = _provider(settings)
    steps = request.max_steps or settings.model_max_steps

    def events():
        channel: queue.Queue = queue.Queue()
        sentinel = object()

        def worker() -> None:
            try:
                run_agent(settings, question, provider, max_steps=steps, on_event=channel.put)
            except Exception as exc:  # pragma: no cover - defensive
                channel.put({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
            finally:
                channel.put(sentinel)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            event = channel.get()
            if event is sentinel:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
