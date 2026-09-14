from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ts_knowledge_agent.agent.runtime import create_provider_from_env, run_agent
from ts_knowledge_agent.config import DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL, Settings, initialize_working_directory
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.schemas import write_schema_files
from ts_knowledge_agent.services.converter import convert_file
from ts_knowledge_agent.services.knowledge_tools import knowledge_list, knowledge_read, knowledge_search, knowledge_status
from ts_knowledge_agent.services.pipeline import run_once
from ts_knowledge_agent.services.scanner import scan_directory
from ts_knowledge_agent.services.scheduler import run_once_with_report, run_scheduler

PROGRAM = "ts-team-kb"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM)
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init")
    init.add_argument("--working-directory", required=True, type=Path)
    init.add_argument("--personal-workspace", required=True)
    init.add_argument("--shared-source-directory", required=True, type=Path)
    init.add_argument("--scan-interval-minutes", type=int, default=60)
    init.add_argument("--shared-knowledge-repository-url", default=DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL)

    sub.add_parser("status")

    scan = sub.add_parser("scan")
    scan.add_argument("--shared-source-directory", type=Path)

    convert = sub.add_parser("convert")
    convert.add_argument("--file", required=True, type=Path)
    convert.add_argument("--output", type=Path)

    run = sub.add_parser("run-once")
    run.add_argument("--sync", action="store_true")
    run.add_argument("--batch-size", type=int, default=25)

    sub.add_parser("schedule")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--member")

    read = sub.add_parser("read")
    read.add_argument("path")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--limit", type=int, default=200)

    listing = sub.add_parser("list")
    listing.add_argument("--member")
    listing.add_argument("--prefix")
    listing.add_argument("--limit", type=int, default=200)

    ask = sub.add_parser("ask"); ask.add_argument("question"); ask.add_argument("--max-steps", type=int, default=6)
    schemas = sub.add_parser("schemas")
    schemas.add_argument("--output", required=True, type=Path)

    return parser


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        if args.scan_interval_minutes < 1:
            parser.error("scan-interval-minutes must be at least 1 minute")
        if not args.personal_workspace.strip():
            parser.error("personal-workspace must not be empty")
        if not str(args.shared_source_directory).strip():
            parser.error("shared-source-directory must not be empty")
        settings = Settings(
            args.personal_workspace.strip(),
            args.shared_source_directory,
            args.working_directory,
            args.working_directory / "knowledge-base" / "ts-team-knowledge-base",
            args.scan_interval_minutes,
            args.shared_knowledge_repository_url,
        )
        try:
            initialize_working_directory(settings)
        except (ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        print(
            f"initialized working_directory={settings.working_directory} personal_workspace={settings.personal_workspace} "
            f"shared_knowledge_repository_directory={settings.shared_knowledge_repository_directory}"
        )
        return 0

    settings = Settings.from_env()

    if args.command == "status":
        _print(knowledge_status(settings))
        return 0

    if args.command == "search":
        _print([hit.__dict__ for hit in knowledge_search(settings, args.query, limit=args.limit, member=args.member)])
        return 0

    if args.command == "read":
        _print(knowledge_read(settings, args.path, offset=args.offset, limit=args.limit).__dict__)
        return 0

    if args.command == "list":
        _print(knowledge_list(settings, member=args.member, prefix=args.prefix, limit=args.limit))
        return 0

    if args.command == "scan":
        state = StateStore(settings.shared_knowledge_repository_directory / "data" / "state.sqlite3")
        try:
            sources = scan_directory(args.shared_source_directory or settings.shared_source_directory)
            for source in sources:
                state.upsert_source(source)
            print(f"scanned={len(sources)}")
        finally:
            state.close()
        return 0

    if args.command == "convert":
        source = args.file.expanduser().resolve()
        output = args.output or settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace / source.stem / f"{source.stem}.md"
        result = convert_file(source, output)
        print(f"converted={result.output_path} bytes={result.bytes_written}")
        return 0

    if args.command == "run-once":
        if args.batch_size < 1:
            parser.error("batch-size must be at least 1")
        summary = run_once_with_report(settings, sync=args.sync, batch_size=args.batch_size)
        print(
            f"scanned={summary.scanned} queued={summary.queued} batches={summary.batches} converted={summary.converted} "
            f"skipped={summary.skipped} failed={summary.failed} missing={summary.missing} indexed={summary.indexed} "
            f"sync={summary.sync_status}"
        )
        return 1 if summary.failed or summary.sync_status in {"blocked_conflict", "push_failed"} else 0

    if args.command == "schedule":
        return run_scheduler(settings)

    if args.command == "ask":
        provider = create_provider_from_env()
        if provider is None:
            print(
                "model provider not configured; set TS_TEAM_KB_MODEL_PROVIDER (openai|anthropic), "
                "TS_TEAM_KB_MODEL_BASE_URL, TS_TEAM_KB_MODEL_API_KEY, TS_TEAM_KB_MODEL_NAME"
            )
            return 2
        result = run_agent(settings, args.question, provider, max_steps=args.max_steps)
        print(json.dumps({"answer": result.answer, "citations": result.citations, "steps": result.steps, "error": result.error, "prompt_version": result.prompt_version}, ensure_ascii=False, indent=2))
        return 1 if result.error else 0
    if args.command == "schemas":
        for path in write_schema_files(args.output):
            print(path)
        return 0

    parser.print_help()
    return 0
