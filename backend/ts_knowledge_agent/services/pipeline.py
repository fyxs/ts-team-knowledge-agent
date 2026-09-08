from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.converter import CONVERTER_VERSION, convert_file
from ts_knowledge_agent.services.indexing import index_converted
from ts_knowledge_agent.services.scanner import SourceFile, scan_directory

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
    skipped:int=0
    failed:int=0
    missing:int=0
    indexed:int=0
    sync_status:str="disabled"

def output_path_for(settings: Settings, relative_path: str) -> Path:
    relative=Path(relative_path)
    document_dir=settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace / relative.parent / relative.stem
    return document_dir / f"{relative.stem}.md"

def run_once(settings: Settings, sync: bool=False, batch_size:int=25, converter=None, on_batch:Callable[[ProcessingBatch],None]|None=None)->RunSummary:
    state=StateStore(settings.shared_knowledge_repository_directory/"data"/"state.sqlite3")
    converted=skipped=failed=0
    try:
        recovered=state.recover_stale_processing()
        sources=scan_directory(settings.shared_source_directory)
        seen={source.relative_path for source in sources}
        for source in sources: state.upsert_source(source)
        pending=[source for source in sources if source.supported and state.needs_conversion(source)]
        batches=plan_batches(pending,batch_size)
        for batch in batches:
            if on_batch: on_batch(batch)
            for source in batch.files:
                output=output_path_for(settings,source.relative_path)
                try:
                    state.record_conversion(source.relative_path,source.sha256,output,CONVERTER_VERSION,"processing")
                    result=convert_file(source.absolute_path,output,converter=converter,mineru_python=settings.mineru_python)
                    state.record_conversion(source.relative_path,source.sha256,result.output_path,CONVERTER_VERSION,"converted")
                    converted+=1
                except Exception as exc:
                    state.record_conversion(source.relative_path,source.sha256,output,CONVERTER_VERSION,"failed_retryable",str(exc))
                    failed+=1
        skipped=len(sources)-len(pending)
        missing=state.mark_missing_sources(seen)
        indexed=index_converted(settings)
        return RunSummary(len(sources),len(pending),len(batches),converted,skipped,failed,missing,indexed)
    finally: state.close()
