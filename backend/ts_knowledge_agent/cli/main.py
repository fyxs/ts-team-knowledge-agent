from __future__ import annotations

import argparse
import getpass
import os
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from ts_knowledge_agent.agent.runtime import create_provider, run_agent
from ts_knowledge_agent.agent.setup import configure_model_interactively
from ts_knowledge_agent.agent.secrets import mask_secret, read_api_key, secret_path, write_api_key
from ts_knowledge_agent.config import (
    DEFAULT_SHARED_KNOWLEDGE_REPOSITORY_URL,
    MIN_SCAN_INTERVAL_MINUTES,
    Settings,
    initialize_working_directory,
)
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.schemas import write_schema_files
from ts_knowledge_agent.services.converter import convert_file
from ts_knowledge_agent.services.knowledge_tools import knowledge_list, knowledge_read, knowledge_search, knowledge_status
from ts_knowledge_agent.services.pipeline import run_once
from ts_knowledge_agent.services.scanner import scan_directory
from ts_knowledge_agent.services.scheduler import is_scan_due, run_once_with_report, run_scheduler

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
    init.add_argument("--skip-model-setup", action="store_true")

    sub.add_parser("status")

    scan = sub.add_parser("scan")
    scan.add_argument("--shared-source-directory", type=Path)

    convert = sub.add_parser("convert")
    convert.add_argument("--file", required=True, type=Path)
    convert.add_argument("--output", type=Path)

    run = sub.add_parser("run-once")
    run.add_argument("--sync", action="store_true")
    run.add_argument("--batch-size", type=int, default=25)
    run.add_argument("--if-due", action="store_true", help="只有距上次运行达到扫描间隔时才执行本轮")

    sub.add_parser("schedule")

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8088)
    serve.add_argument("--skip-preflight", action="store_true")

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

    ask = sub.add_parser("ask"); ask.add_argument("question"); ask.add_argument("--max-steps", type=int, default=None)
    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_action")
    config_sub.add_parser("show")
    config_set = config_sub.add_parser("set")
    config_set.add_argument("--provider")
    config_set.add_argument("--model")
    config_set.add_argument("--base-url")
    config_set.add_argument("--max-tokens", type=int)
    config_set.add_argument("--max-steps", type=int)
    config_key = config_sub.add_parser("set-key")
    config_key.add_argument("--from-file", dest="key_file", help="从文件读取密钥（适合不方便交互输入时）")
    config_key.add_argument("value", nargs="?", help=argparse.SUPPRESS)
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
        if args.scan_interval_minutes < MIN_SCAN_INTERVAL_MINUTES:
            parser.error(f"scan-interval-minutes must be at least {MIN_SCAN_INTERVAL_MINUTES} minutes")
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
        config_path = settings.working_directory / "ts-kb.json"
        if args.skip_model_setup or not sys.stdin.isatty():
            print("model setup skipped; run ts-team-kb config set / config set-key later")
        else:
            configure_model_interactively(settings).write_file(config_path)
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
        if args.if_due and not is_scan_due(settings):
            print(f"skipped=not_due scan_interval_minutes={settings.scan_interval_minutes}")
            return 0
        summary = run_once_with_report(settings, sync=args.sync, batch_size=args.batch_size)
        print(
            f"scanned={summary.scanned} queued={summary.queued} batches={summary.batches} converted={summary.converted} "
            f"skipped={summary.skipped} failed={summary.failed} missing={summary.missing} indexed={summary.indexed} "
            f"sync={summary.sync_status}"
        )
        return 1 if summary.failed or summary.sync_status in {"blocked_conflict", "push_failed"} else 0

    if args.command == "schedule":
        return run_scheduler(settings)

    if args.command == "serve":
        from ts_knowledge_agent.api.main import resolve_web_dist
        from ts_knowledge_agent.services.preflight import format_report, has_blocking_errors, run_preflight

        results = run_preflight(settings, web_dist=resolve_web_dist())
        print(format_report(results))
        if has_blocking_errors(results) and not args.skip_preflight:
            print("")
            print("启动已中止：存在阻塞项。修正后重试，或加 --skip-preflight 强制启动。")
            return 2
        if args.host not in {"127.0.0.1", "localhost"}:
            print("")
            print(f"注意：正在监听 {args.host}，界面可被网络内其它机器访问。")
            print("      界面上的推送操作会使用本机的 Git 凭据，请确认网络范围可信。")
        print("")
        print(f"服务地址：http://{args.host}:{args.port}/")
        import uvicorn

        uvicorn.run("ts_knowledge_agent.api.main:app", host=args.host, port=args.port)
        return 0

    if args.command == "ask":
        provider = create_provider(settings)
        if provider is None:
            print(
                "model provider not configured; set TS_TEAM_KB_MODEL_PROVIDER (openai|anthropic), "
                "TS_TEAM_KB_MODEL_BASE_URL, TS_TEAM_KB_MODEL_API_KEY, TS_TEAM_KB_MODEL_NAME"
            )
            return 2
        max_steps = args.max_steps or settings.model_max_steps
        result = run_agent(settings, args.question, provider, max_steps=max_steps)
        print(json.dumps({"answer": result.answer, "citations": result.citations, "steps": result.steps, "error": result.error, "prompt_version": result.prompt_version}, ensure_ascii=False, indent=2))
        return 1 if result.error else 0
    if args.command == "config":
        config_path = Path(os.getenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json")))
        action = getattr(args, "config_action", None)
        if action == "show":
            print(json.dumps({
                "config_path": str(config_path),
                "config_exists": config_path.is_file(),
                "provider": settings.model_provider or "(unset, defaults to openai-compatible)",
                "model": settings.model_name or "(unset)",
                "base_url": settings.model_base_url or "(provider default)",
                "max_tokens": settings.model_max_tokens,
                "api_key": mask_secret(read_api_key(settings.working_directory)),
                "api_key_path": str(secret_path(settings.working_directory)),
                "env_overrides": {name: True for name in (
                    "TS_TEAM_KB_MODEL_PROVIDER", "TS_TEAM_KB_MODEL_NAME",
                    "TS_TEAM_KB_MODEL_BASE_URL", "TS_TEAM_KB_MODEL_API_KEY",
                    "TS_TEAM_KB_MODEL_MAX_TOKENS") if os.getenv(name)},
            }, ensure_ascii=False, indent=2))
            return 0
        if action == "set":
            updates = {}
            if args.provider: updates["model_provider"] = args.provider.strip().lower()
            if args.model: updates["model_name"] = args.model.strip()
            if args.base_url is not None: updates["model_base_url"] = args.base_url.strip()
            if args.max_tokens: updates["model_max_tokens"] = int(args.max_tokens)
            if args.max_steps: updates["model_max_steps"] = int(args.max_steps)
            if not updates:
                parser.error("config set requires at least one of --provider, --model, --base-url, --max-tokens")
            if not config_path.is_file():
                parser.error(f"configuration file not found: {config_path}; run ts-team-kb init first")
            replace(settings, **updates).write_file(config_path)
            print(json.dumps({"updated": updates, "config_path": str(config_path)}, ensure_ascii=False, indent=2))
            return 0
        if action == "set-key":
            if getattr(args, "value", None):
                print(
                    "refused: do not pass the api key as a command argument;\n"
                    "it would leak into shell history and logs.\n"
                    "use the interactive prompt (ts-team-kb config set-key) "
                    "or --from-file <path>."
                )
                return 2
            key_file = getattr(args, "key_file", None)
            if key_file:
                source = Path(key_file).expanduser()
                if not source.is_file():
                    print(f"key file not found: {source}")
                    return 2
                api_key = source.read_text(encoding="utf-8-sig").strip()
            else:
                api_key = getpass.getpass("model API key (input hidden): ").strip()
            if not api_key:
                print("empty input, nothing written")
                return 2
            path = write_api_key(settings.working_directory, api_key)
            print(f"api key stored at {path} (never commit this file)")
            return 0
        parser.error("config requires an action: show | set | set-key")
    if args.command == "schemas":
        for path in write_schema_files(args.output):
            print(path)
        return 0

    parser.print_help()
    return 0
