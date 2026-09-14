from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from ts_knowledge_agent.config import DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL, Settings, clone_knowledge_repo, initialize_working_directory
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.services.converter import convert_file
from ts_knowledge_agent.services.indexing import search_converted
from ts_knowledge_agent.services.knowledge_tools import (
    knowledge_list,
    knowledge_read,
    knowledge_search,
    knowledge_status,
)
from ts_knowledge_agent.schemas import write_schema_files
from ts_knowledge_agent.services.pipeline import run_once
from ts_knowledge_agent.services.scheduler import run_once_with_report, run_scheduler
from ts_knowledge_agent.services.scanner import scan_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ts-kb")
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init")
    init.add_argument("--working-directory", required=True, type=Path)
    init.add_argument("--personal-workspace", required=True)
    init.add_argument("--shared-source-directory", required=True, type=Path)
    init.add_argument("--scan-interval-minutes", type=int, default=60)
    init.add_argument("--shared-knowledge-repository-url", default=DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL)
    sub.add_parser("status")
    scan = sub.add_parser("scan"); scan.add_argument("--shared-source-directory", type=Path)
    convert = sub.add_parser("convert"); convert.add_argument("--file", required=True, type=Path); convert.add_argument("--output", type=Path)
    run = sub.add_parser("run-once"); run.add_argument("--sync", action="store_true"); run.add_argument("--batch-size", type=int, default=25)
    sub.add_parser("schedule")
    search = sub.add_parser("search"); search.add_argument("query")
    schemas = sub.add_parser("schemas"); schemas.add_argument("--output", required=True, type=Path)
    ks = sub.add_parser("knowledge-search"); ks.add_argument("query"); ks.add_argument("--limit", type=int, default=5); ks.add_argument("--member")
    kr = sub.add_parser("knowledge-read"); kr.add_argument("path"); kr.add_argument("--offset", type=int, default=0); kr.add_argument("--limit", type=int, default=200)
    kl = sub.add_parser("knowledge-list"); kl.add_argument("--member"); kl.add_argument("--prefix"); kl.add_argument("--limit", type=int, default=200)
    sub.add_parser("knowledge-status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(); args = parser.parse_args(argv)
    if args.command == "init":
        if args.scan_interval_minutes < 1: parser.error("scan-interval-minutes must be at least 1 minute")
        if not args.personal_workspace.strip(): parser.error("personal-workspace must not be empty")
        if not str(args.shared_source_directory).strip(): parser.error("shared-source-directory must not be empty")
        settings = Settings(args.personal_workspace.strip(), args.shared_source_directory, args.working_directory, args.working_directory / "knowledge-base" / "ts-team-knowledge-base", args.scan_interval_minutes, args.shared_knowledge_repository_url)
        try: initialize_working_directory(settings)
        except (ValueError, RuntimeError) as exc: parser.error(str(exc))
        print(f"initialized working_directory={settings.working_directory} personal_workspace={settings.personal_workspace} shared_knowledge_repository_directory={settings.shared_knowledge_repository_directory}"); return 0
    if args.command is None:
        parser.print_help(); return 0
    settings = Settings.from_env()
    if args.command == "scan":
        state = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
        try:
            sources = scan_directory(args.shared_source_directory or settings.shared_source_directory)
            for source in sources: state.upsert_source(source)
            print(f"scanned={len(sources)}")
        finally: state.close()
        return 0
    if args.command == "convert":
        source = args.file.expanduser().resolve(); output = args.output or settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace / "converted" / f"{source.stem}.md"; result = convert_file(source, output); print(f"converted={result.output_path} bytes={result.bytes_written}"); return 0
    if args.command == "run-once":
        if args.batch_size < 1: parser.error("batch-size must be at least 1")
        summary = run_once_with_report(settings, sync=args.sync, batch_size=args.batch_size); print(f"scanned={summary.scanned} queued={summary.queued} batches={summary.batches} converted={summary.converted} skipped={summary.skipped} failed={summary.failed} missing={summary.missing} indexed={summary.indexed} sync={summary.sync_status}"); return 1 if summary.failed or summary.sync_status in {"blocked_conflict", "push_failed"} else 0
    if args.command == "schedule": return run_scheduler(settings)
    if args.command == "status":
        state = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
        try: print(f"sources={len(state.list_sources())} conversions={len(state.list_conversions())} personal_workspace={settings.personal_workspace}")
        finally: state.close()
        return 0
    if args.command == "knowledge-search":
        import json as _json
        hits = knowledge_search(settings, args.query, limit=args.limit, member=args.member)
        print(_json.dumps([hit.__dict__ for hit in hits], ensure_ascii=False, indent=2))
        return 0
    if args.command == "knowledge-read":
        import json as _json
        document = knowledge_read(settings, args.path, offset=args.offset, limit=args.limit)
        print(_json.dumps(document.__dict__, ensure_ascii=False, indent=2))
        return 0
    if args.command == "knowledge-list":
        import json as _json
        print(_json.dumps(knowledge_list(settings, member=args.member, prefix=args.prefix, limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "knowledge-status":
        import json as _json
        print(_json.dumps(knowledge_status(settings), ensure_ascii=False, indent=2))
        return 0
    if args.command == "schemas":
        for path in write_schema_files(args.output): print(path)
        return 0
    if args.command == "search":
        for row in search_converted(settings, args.query): print(f"{row['path']} | {row['title']} | {row['snippet']}")
        return 0
    parser.print_help(); return 0
