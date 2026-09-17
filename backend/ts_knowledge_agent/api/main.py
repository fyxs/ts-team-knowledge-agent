from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ts_knowledge_agent.agent.runtime import create_provider, run_agent
from ts_knowledge_agent.agent.secrets import read_api_key, secret_path
from ts_knowledge_agent.agent.setup import mask_key
from ts_knowledge_agent.adapters.git_sync import pull_repository, push_repository
from ts_knowledge_agent.config import MIN_SCAN_INTERVAL_MINUTES, Settings
from ts_knowledge_agent.services.knowledge_tools import knowledge_asset, knowledge_document
from ts_knowledge_agent.services.scheduler import run_once_with_report
from ts_knowledge_agent.services.sessions import (
    SessionStore,
    session_database_path,
)
from ts_knowledge_agent.services.usage import TraceCollector, append_trace

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
    session_id: str | None = None
    max_steps: int | None = None


class ConfigPayload(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    max_steps: int | None = None
    scan_interval_minutes: int | None = None


class RunRequest(BaseModel):
    sync: bool = True
    batch_size: int = 25


# 手动触发的一轮扫描：后台线程执行，前端轮询 /api/v1/run 获取进度
_run_state: dict = {"running": False, "started_at": None, "last": None}


def last_run_report(settings: Settings) -> dict | None:
    report = settings.working_directory / "logs" / "runs.jsonl"
    if not report.is_file():
        return None
    for line in reversed(report.read_text(encoding="utf-8", errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


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
        "scan_interval_minutes": settings.scan_interval_minutes,
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
    if payload.scan_interval_minutes is not None:
        if int(payload.scan_interval_minutes) < MIN_SCAN_INTERVAL_MINUTES:
            raise HTTPException(
                status_code=400,
                detail=f"scan_interval_minutes must be at least {MIN_SCAN_INTERVAL_MINUTES}",
            )
        updates["scan_interval_minutes"] = int(payload.scan_interval_minutes)
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


@app.get("/api/v1/sessions")
def list_sessions() -> dict:
    settings = load_settings()
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        return {"sessions": [item.to_dict() for item in store.list_sessions()]}
    finally:
        store.close()


@app.post("/api/v1/sessions")
def create_session() -> dict:
    settings = load_settings()
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        return store.create_session().to_dict()
    finally:
        store.close()


@app.get("/api/v1/sessions/search")
def search_session_history(q: str = "", limit: int = 20) -> dict:
    """在会话历史里按关键词检索，返回命中的会话、消息与上下文片段。"""

    query = (q or "").strip()
    if not query:
        return {"query": "", "hits": []}
    settings = load_settings()
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        return {
            "query": query,
            "hits": store.search_messages(query, limit=max(1, min(limit, 100))),
        }
    finally:
        store.close()


@app.get("/api/v1/sessions/{session_id}/messages")
def session_messages(session_id: str) -> dict:
    settings = load_settings()
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return {"session": session.to_dict(), "messages": store.list_messages(session_id)}
    finally:
        store.close()


class SessionRenamePayload(BaseModel):
    title: str


@app.patch("/api/v1/sessions/{session_id}")
def rename_session(session_id: str, payload: SessionRenamePayload) -> dict:
    """重命名会话；标题超长按上限截断，空白标题拒绝。"""

    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    settings = load_settings()
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        store.rename_session(session_id, title)
        updated = store.get_session(session_id)
        return updated.to_dict() if updated else {}
    finally:
        store.close()


@app.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """删除会话及其全部消息。"""

    settings = load_settings()
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        store.delete_session(session_id)
        return {"deleted": True, "session_id": session_id}
    finally:
        store.close()


def _persist_turn(store: SessionStore, session_id: str, question: str, collector, result) -> None:
    """把一轮对话写入本机会话库：用户消息、工具过程、回答或错误。"""

    store.append_message(session_id, "user", {"content": question})
    steps = [
        {"name": entry.get("tool"), "detail": entry.get("query") or entry.get("path") or "", "status": "done"}
        for entry in collector.steps
    ]
    if steps:
        store.append_message(session_id, "process", {"steps": steps, "running": False})
    if result is not None and result.error:
        store.append_message(session_id, "error", {"message": str(result.error)})
    elif result is not None:
        store.append_message(
            session_id,
            "answer",
            {
                "content": result.answer or "",
                "citations": list(result.citations or []),
                "sources": list(result.sources or []),
                "steps": result.steps,
                "retrieved": bool(result.retrieved),
            },
        )


@app.post("/api/v1/chat")
def chat(request: ChatRequest) -> dict:
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    settings = load_settings()
    provider = _provider(settings)
    steps = request.max_steps or settings.model_max_steps
    collector = TraceCollector()
    result = run_agent(settings, question, provider, max_steps=steps, on_event=collector)
    append_trace(settings.working_directory, collector.to_record(settings.personal_workspace, "web"))
    store = SessionStore(session_database_path(settings.working_directory))
    try:
        session = store.ensure_session(request.session_id, question)
        _persist_turn(store, session.id, question, collector, result)
    finally:
        store.close()
    return {
        "answer": result.answer,
        "citations": result.citations,
        "sources": result.sources,
        "steps": result.steps,
        "error": result.error,
        "retrieved": result.retrieved,
        "session_id": session.id,
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
                collector = TraceCollector()

                def emit(event: dict) -> None:
                    collector(event)
                    channel.put(event)

                result = run_agent(settings, question, provider, max_steps=steps, on_event=emit)
                append_trace(settings.working_directory, collector.to_record(settings.personal_workspace, "web"))
                store = SessionStore(session_database_path(settings.working_directory))
                try:
                    session = store.ensure_session(request.session_id, question)
                    _persist_turn(store, session.id, question, collector, result)
                finally:
                    store.close()
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


@app.post("/api/v1/run")
def trigger_run(request: RunRequest | None = None) -> dict:
    """手动触发一轮扫描与转换；已在运行时返回 busy，不排队也不并发。"""
    options = request or RunRequest()
    if _run_state["running"]:
        return {"status": "busy", "started_at": _run_state["started_at"]}
    if options.batch_size < 1:
        raise HTTPException(status_code=400, detail="batch_size must be at least 1")
    settings = load_settings()

    def worker() -> None:
        _run_state["running"] = True
        _run_state["started_at"] = datetime.now(timezone.utc).isoformat()
        try:
            summary = run_once_with_report(settings, sync=options.sync, batch_size=options.batch_size)
            _run_state["last"] = {
                "status": "finished",
                "scanned": summary.scanned,
                "queued": summary.queued,
                "converted": summary.converted,
                "warned": summary.warned,
                "skipped": summary.skipped,
                "failed": summary.failed,
                "indexed": summary.indexed,
                "sync_status": summary.sync_status,
                "reason_counts": summary.reason_counts,
            }
        except Exception as exc:  # pragma: no cover - 由运行报告记录细节
            _run_state["last"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        finally:
            _run_state["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started"}


@app.get("/api/v1/run")
def run_status() -> dict:
    settings = load_settings()
    return {
        "running": _run_state["running"],
        "started_at": _run_state["started_at"],
        "last": _run_state["last"],
        "report": last_run_report(settings),
    }


@app.post("/api/v1/repository/pull")
def repository_pull() -> dict:
    settings = load_settings()
    result = pull_repository(settings.shared_knowledge_repository_directory)
    return {"status": result.status, "commit": result.commit, "message": result.message}


@app.post("/api/v1/repository/push")
def repository_push() -> dict:
    settings = load_settings()
    result = push_repository(settings.shared_knowledge_repository_directory)
    return {"status": result.status, "commit": result.commit, "message": result.message}


@app.get("/api/v1/knowledge/document")
def get_knowledge_document(path: str, offset: int = 0, limit: int = 200) -> dict:
    """读取被引用文档的正文，供「来源阅读」使用。

    边界（members/ 之内、必须是 .md、只读）全部由服务层判定；
    这里只负责把两类失败映射成 400 / 404。
    """

    settings = load_settings()
    try:
        document = knowledge_document(settings, path, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "path": document.path,
        "title": document.title,
        "content": document.content,
        "offset": document.offset,
        "returned_lines": document.returned_lines,
        "total_lines": document.total_lines,
        "truncated": document.truncated,
    }


@app.get("/api/v1/knowledge/asset")
def get_knowledge_asset(path: str) -> FileResponse:
    """读取文档内的相对资源（图片），与正文同一套边界，另加后缀白名单。"""

    settings = load_settings()
    try:
        target, media_type = knowledge_asset(settings, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(target, media_type=media_type)


def resolve_web_dist() -> Path | None:
    """定位前端构建产物：优先环境变量，其次仓库内的 frontend/dist。"""
    configured = os.getenv("TS_KB_WEB_DIST", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        return candidate if (candidate / "index.html").is_file() else None
    # 发布安装：前端产物随包分发（ts_knowledge_agent/web/），成员机无需 Node。
    packaged = Path(__file__).resolve().parent.parent / "web"
    if (packaged / "index.html").is_file():
        return packaged
    # 开发环境：仓库内的 frontend/dist
    default = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return default if (default / "index.html").is_file() else None


def mount_web(application: FastAPI, dist: Path) -> None:
    """托管前端产物：静态资源 + SPA 兜底。必须在所有 API 路由之后调用。"""
    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="web-assets")

    @application.get("/", include_in_schema=False)
    def web_index() -> FileResponse:
        return FileResponse(dist / "index.html")

    @application.get("/{path:path}", include_in_schema=False)
    def web_fallback(path: str) -> FileResponse:
        target = (dist / path).resolve()
        try:
            target.relative_to(dist.resolve())
        except ValueError:
            return FileResponse(dist / "index.html")
        if target.is_file():
            return FileResponse(target)
        return FileResponse(dist / "index.html")


def configure_web(application: FastAPI) -> Path | None:
    dist = resolve_web_dist()
    if dist is not None:
        mount_web(application, dist)
    return dist


configure_web(app)
