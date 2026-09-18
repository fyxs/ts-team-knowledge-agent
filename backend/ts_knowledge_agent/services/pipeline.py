from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.adapters.git_sync import sync_repository
from ts_knowledge_agent.services.secret_scan import quarantine_document, scan_markdown_file
from ts_knowledge_agent.services.feedback import FeedbackRecord, append_feedback, has_open_feedback
from ts_knowledge_agent.services.converter import (
    CONVERTER_VERSION,
    convert_file,
    conversion_cost_class,
)
from ts_knowledge_agent.services.postprocess import ensure_markdown_title
from ts_knowledge_agent.services.indexing import index_converted
from ts_knowledge_agent.services.scanner import SourceFile, scan_directory
from ts_knowledge_agent.services.run_lock import RunLock
from ts_knowledge_agent.services.quality import inspect_markdown_file
from ts_knowledge_agent.services.usage import rollup_usage
from ts_knowledge_agent.services.registries import export_review_records, write_knowledge_registry, write_source_registry

@dataclass(frozen=True)
class ProcessingBatch:
    number: int
    files: tuple[SourceFile, ...]

def plan_batches(files: list[SourceFile], batch_size: int) -> list[ProcessingBatch]:
    """按车道（轻量优先）与路径分批，让新加入的 md/txt 不被 MinerU 重活堵在队尾。

    排序键只在**这里**收敛：调用方不要再排一遍，否则会被本函数覆盖
    （实测出现过「外层按代价排序、内层又按路径重排」导致轻量优先完全失效）。
    """

    if batch_size < 1: raise ValueError("batch size must be at least 1")
    ordered=sorted(files,key=lambda item:(conversion_cost_class(item.absolute_path), item.relative_path.lower()))
    return [ProcessingBatch(i,tuple(ordered[start:start+batch_size])) for i,start in enumerate(range(0,len(ordered),batch_size),1)]

@dataclass(frozen=True)
class RunSummary:
    scanned:int
    queued:int=0
    batches:int=0
    converted:int=0
    warned:int=0
    skipped:int=0
    failed:int=0
    missing:int=0
    indexed:int=0
    sync_status:str="disabled"
    reason_counts: dict[str,int] = field(default_factory=dict)

LANE_ALL = "all"
LANE_LIGHT = "light"
LANE_HEAVY = "heavy"
LANE_CHOICES = (LANE_ALL, LANE_LIGHT, LANE_HEAVY)
# 轻量车道持独立锁：md/txt 复制不该被 MinerU 重活的锁挡在门外（也不能嵌在它里面）
LANE_LOCK_NAMES = {LANE_ALL: "run.lock", LANE_LIGHT: "light.lock", LANE_HEAVY: "run.lock"}


def lane_of(source: SourceFile) -> str:
    """来源所属车道：轻量（md/txt/xlsx）或重活（MinerU 转换）。"""

    return LANE_LIGHT if conversion_cost_class(source.absolute_path) == 0 else LANE_HEAVY


def output_path_for(settings: Settings, relative_path: str) -> Path:
    relative=Path(relative_path)
    document_dir=settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace / relative.parent / relative.stem
    return document_dir / f"{relative.stem}.md"

def run_once(settings: Settings, sync: bool=False, batch_size:int=25, converter=None, on_batch:Callable[[ProcessingBatch],None]|None=None, lane: str=LANE_ALL)->RunSummary:
    """跑一轮。lane=light/heavy 时只处理该车道的来源，并使用该车道自己的锁。"""

    if lane not in LANE_LOCK_NAMES:
        raise ValueError("unknown lane: " + lane + "（可选 " + " / ".join(LANE_CHOICES) + "）")
    with RunLock(settings.working_directory, name=LANE_LOCK_NAMES[lane]):
        return _run_once_locked(settings, sync, batch_size, converter, on_batch, lane=lane)

def log_conversion_timing(settings: Settings, source, converter_label: str,
                          seconds: float, status: str) -> None:
    """逐篇转换审计：路径 / 转换器 / 耗时 / 结果。

    没有它就无法区分"在慢慢跑重活"与"卡住了"（实测因此误判多次，
    一度把 15 分钟的 PDF 推理当成流水线卡死）。

    status："ok" = 转换成功；"failed:<异常类型>" = 失败或超时（失败路径同样要留痕，
    否则最需要耗时的场景反而没有记录）。
    """
    try:
        log_dir = settings.working_directory / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "source_suffix": source.absolute_path.suffix.lower(),
            "source_name": source.absolute_path.name,
            "converter": converter_label,
            "seconds": round(seconds, 2),
            "status": status,
        }
        with (log_dir / "conversions.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _run_once_locked(settings: Settings, sync: bool=False, batch_size:int=25, converter=None, on_batch:Callable[[ProcessingBatch],None]|None=None, lane: str=LANE_ALL)->RunSummary:
    state=StateStore(settings.shared_knowledge_repository_directory/"data"/"state.sqlite3")
    converted=warned=skipped=failed=0; reason_counts:dict[str,int]={}
    try:
        recovered=state.recover_stale_processing()
        if recovered: reason_counts["stale_processing_recovered"]=recovered
        sources=scan_directory(settings.shared_source_directory)
        seen={source.relative_path for source in sources}
        for source in sources: state.upsert_source(source)
        state.backfill_source_statuses()
        pending=[]
        excluded=set(settings.excluded_source_paths)
        for source in sources:
            if source.relative_path in excluded:
                reason_counts["excluded"]=reason_counts.get("excluded",0)+1
                state.update_source_status(source.relative_path,"ignored")
                continue
            reason="unsupported" if not source.supported else state.conversion_reason(source)
            reason_counts[reason]=reason_counts.get(reason,0)+1
            if not source.supported:
                state.update_source_status(source.relative_path,"ignored")
            elif reason!="unchanged":
                if lane != LANE_ALL and lane_of(source) != lane:
                    # 另一条车道的活：不改状态、不计失败，留给它自己处理
                    reason_counts["deferred_to_other_lane"]=reason_counts.get("deferred_to_other_lane",0)+1
                    continue
                pending.append((source,reason))
        batches=plan_batches([source for source,_ in pending], batch_size)
        reason_by_path={source.relative_path:reason for source,reason in pending}
        for batch in batches:
            if on_batch: on_batch(batch)
            for source in batch.files:
                output=output_path_for(settings,source.relative_path); reason=reason_by_path[source.relative_path]
                _started = time.perf_counter()
                try:
                    state.record_conversion(source.relative_path,source.sha256,output,CONVERTER_VERSION,"processing",reason=reason)
                    result=convert_file(source.absolute_path,output,converter=converter,mineru_python=settings.mineru_python,
                                             mineru_timeout_seconds=settings.mineru_timeout_seconds,
                                             mineru_chunk_pages=settings.mineru_chunk_pages)
                    log_conversion_timing(settings, source, result.converter,
                                          time.perf_counter() - _started, "ok")
                    if not result.from_source:
                        ensure_markdown_title(result.output_path, source.absolute_path.stem)
                    quality = inspect_markdown_file(result.output_path)
                    warning_message = None if quality.ok else "; ".join(quality.errors)
                    if warning_message and not result.from_source:
                        # 工具产物质量问题：可能由转换引入，隔离出共享仓库，不入库
                        quarantine_document(settings.working_directory, settings.shared_knowledge_repository_directory, result.output_path.parent)
                        state.record_conversion(source.relative_path,source.sha256,result.output_path,result.converter,"quality_failed",warning_message,reason="quality_failed")
                        state.update_source_status(source.relative_path,"quality_failed")
                        reason_counts["quality_failed"]=reason_counts.get("quality_failed",0)+1
                        failed += 1
                        continue
                    secret = scan_markdown_file(result.output_path)
                    if not secret.ok:
                        quarantine_document(settings.working_directory, settings.shared_knowledge_repository_directory, result.output_path.parent)
                        state.record_conversion(source.relative_path,source.sha256,result.output_path,result.converter,"blocked_secret",secret.summary(),reason="blocked_secret")
                        if not has_open_feedback(settings.working_directory, source.sha256, "credential_exposure"):
                            append_feedback(settings.working_directory, FeedbackRecord(
                                source_relative_path=source.relative_path,
                                source_sha256=source.sha256,
                                file_type=source.absolute_path.suffix.lower(),
                                converter="secret-scan",
                                converter_version=result.converter,
                                output_path=str(output),
                                category="credential_exposure",
                                description=secret.summary(),
                                expected="移除或脱敏凭据后重新转换，再进入共享仓",
                                source_issue=True,
                                adapter_issue=False,
                                resolution="open",
                                review_status="open",
                            ))
                        state.update_source_status(source.relative_path,"blocked_secret")
                        reason_counts["blocked_secret"]=reason_counts.get("blocked_secret",0)+1
                        failed += 1
                        continue
                    status = "quality_warned" if warning_message else "converted"
                    state.record_conversion(source.relative_path,source.sha256,result.output_path,result.converter,status,reason=reason,warning_message=warning_message)
                    state.update_source_status(source.relative_path,status)
                    if warning_message:
                        warned+=1
                        reason_counts["source_quality_warning"]=reason_counts.get("source_quality_warning",0)+1
                        if not has_open_feedback(settings.working_directory, source.sha256, "source_quality_warning"):
                            append_feedback(settings.working_directory, FeedbackRecord(
                                source_relative_path=source.relative_path,
                                source_sha256=source.sha256,
                                file_type=source.absolute_path.suffix.lower(),
                                converter="source-copy",
                                converter_version=result.converter,
                                output_path=str(result.output_path),
                                category="source_quality_warning",
                                description=warning_message,
                                expected="源文件自带的质量问题不影响入库；请修源文件后重扫，或确认可接受并关闭该记录",
                                source_issue=True,
                                adapter_issue=False,
                                resolution="open",
                                review_status="open",
                            ))
                    else:
                        converted+=1
                except Exception as exc:
                    # 失败/超时同样记耗时：这类记录最能用来区分「卡住」与「在跑」
                    log_conversion_timing(settings, source, CONVERTER_VERSION,
                                          time.perf_counter() - _started,
                                          "failed:" + type(exc).__name__)
                    state.record_conversion(source.relative_path,source.sha256,output,CONVERTER_VERSION,"failed_retryable",str(exc),reason=reason)
                    state.update_source_status(source.relative_path,"failed_retryable")
                    failed+=1
        skipped=reason_counts.get("unchanged",0)+reason_counts.get("unsupported",0)+reason_counts.get("excluded",0)
        missing=state.mark_missing_sources(seen)
        indexed=index_converted(settings)
        write_source_registry(settings)
        write_knowledge_registry(settings)
        rollup_usage(settings.working_directory, settings.shared_knowledge_repository_directory, settings.personal_workspace)
        export_review_records(settings)
        sync_status="disabled"
        if sync:
            if reason_counts.get("blocked_secret"): sync_status="blocked_secret"
            else: sync_status=sync_repository(settings.shared_knowledge_repository_directory,"Sync knowledge from conversion run").status
        return RunSummary(scanned=len(sources),queued=len(pending),batches=len(batches),converted=converted,warned=warned,skipped=skipped,failed=failed,missing=missing,indexed=indexed,sync_status=sync_status,reason_counts=reason_counts)
    finally: state.close()
