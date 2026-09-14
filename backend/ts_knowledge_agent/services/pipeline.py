from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.adapters.git_sync import sync_repository
from ts_knowledge_agent.services.secret_scan import quarantine_document, scan_markdown_file
from ts_knowledge_agent.services.feedback import FeedbackRecord, append_feedback, has_open_feedback
from ts_knowledge_agent.services.converter import CONVERTER_VERSION, convert_file
from ts_knowledge_agent.services.indexing import index_converted
from ts_knowledge_agent.services.scanner import SourceFile, scan_directory
from ts_knowledge_agent.services.run_lock import RunLock
from ts_knowledge_agent.services.quality import inspect_markdown_file
from ts_knowledge_agent.services.registries import export_review_records, write_knowledge_registry, write_source_registry

@dataclass(frozen=True)
class ProcessingBatch:
    number: int
    files: tuple[SourceFile, ...]

def plan_batches(files: list[SourceFile], batch_size: int) -> list[ProcessingBatch]:
    if batch_size < 1: raise ValueError("batch size must be at least 1")
    ordered=sorted(files,key=lambda item:item.relative_path.lower())
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

def output_path_for(settings: Settings, relative_path: str) -> Path:
    relative=Path(relative_path)
    document_dir=settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace / relative.parent / relative.stem
    return document_dir / f"{relative.stem}.md"

def run_once(settings: Settings, sync: bool=False, batch_size:int=25, converter=None, on_batch:Callable[[ProcessingBatch],None]|None=None)->RunSummary:
    with RunLock(settings.working_directory):
        return _run_once_locked(settings, sync, batch_size, converter, on_batch)

def _run_once_locked(settings: Settings, sync: bool=False, batch_size:int=25, converter=None, on_batch:Callable[[ProcessingBatch],None]|None=None)->RunSummary:
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
            elif reason!="unchanged": pending.append((source,reason))
        batches=plan_batches([source for source,_ in pending],batch_size)
        reason_by_path={source.relative_path:reason for source,reason in pending}
        for batch in batches:
            if on_batch: on_batch(batch)
            for source in batch.files:
                output=output_path_for(settings,source.relative_path); reason=reason_by_path[source.relative_path]
                try:
                    state.record_conversion(source.relative_path,source.sha256,output,CONVERTER_VERSION,"processing",reason=reason)
                    result=convert_file(source.absolute_path,output,converter=converter,mineru_python=settings.mineru_python)
                    quality = inspect_markdown_file(result.output_path)
                    warning_message = None if quality.ok else "; ".join(quality.errors)
                    if warning_message and not result.from_source:
                        # 工具产物质量问题：可能由转换引入，隔离出共享仓库，不入库
                        quarantine_document(settings.working_directory, settings.shared_knowledge_repository_directory, result.output_path.parent)
                        state.record_conversion(source.relative_path,source.sha256,result.output_path,CONVERTER_VERSION,"quality_failed",warning_message,reason="quality_failed")
                        state.update_source_status(source.relative_path,"quality_failed")
                        reason_counts["quality_failed"]=reason_counts.get("quality_failed",0)+1
                        failed += 1
                        continue
                    secret = scan_markdown_file(result.output_path)
                    if not secret.ok:
                        quarantine_document(settings.working_directory, settings.shared_knowledge_repository_directory, result.output_path.parent)
                        state.record_conversion(source.relative_path,source.sha256,result.output_path,CONVERTER_VERSION,"blocked_secret",secret.summary(),reason="blocked_secret")
                        if not has_open_feedback(settings.working_directory, source.sha256, "credential_exposure"):
                            append_feedback(settings.working_directory, FeedbackRecord(
                                source_relative_path=source.relative_path,
                                source_sha256=source.sha256,
                                file_type=source.absolute_path.suffix.lower(),
                                converter="secret-scan",
                                converter_version=CONVERTER_VERSION,
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
                    state.record_conversion(source.relative_path,source.sha256,result.output_path,CONVERTER_VERSION,status,reason=reason,warning_message=warning_message)
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
                                converter_version=CONVERTER_VERSION,
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
                    state.record_conversion(source.relative_path,source.sha256,output,CONVERTER_VERSION,"failed_retryable",str(exc),reason=reason)
                    state.update_source_status(source.relative_path,"failed_retryable")
                    failed+=1
        skipped=reason_counts.get("unchanged",0)+reason_counts.get("unsupported",0)+reason_counts.get("excluded",0)
        missing=state.mark_missing_sources(seen)
        indexed=index_converted(settings)
        write_source_registry(settings)
        write_knowledge_registry(settings)
        export_review_records(settings)
        sync_status="disabled"
        if sync:
            if reason_counts.get("blocked_secret"): sync_status="blocked_secret"
            else: sync_status=sync_repository(settings.shared_knowledge_repository_directory,"Sync knowledge from conversion run").status
        return RunSummary(scanned=len(sources),queued=len(pending),batches=len(batches),converted=converted,warned=warned,skipped=skipped,failed=failed,missing=missing,indexed=indexed,sync_status=sync_status,reason_counts=reason_counts)
    finally: state.close()
