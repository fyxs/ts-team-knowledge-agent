from __future__ import annotations

import argparse
import platform
import subprocess
from datetime import datetime, timezone
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
from ts_knowledge_agent.services.governance import publish_inspection_report
from ts_knowledge_agent.services.member_space import ensure_member_space
from ts_knowledge_agent.services.governance import publish_evaluation_report
from ts_knowledge_agent.services.inspection import (
    DEFAULT_INSPECTION_INTERVAL_MINUTES,
    append_inspection_run,
    inspect_knowledge_base,
    is_inspection_due,
    write_inspection_report,
)
from ts_knowledge_agent.schemas import write_schema_files
from ts_knowledge_agent.services.converter import convert_file
from ts_knowledge_agent.services.knowledge_tools import knowledge_list, knowledge_read, knowledge_search, knowledge_status
from ts_knowledge_agent.services.pipeline import run_once
from ts_knowledge_agent.services.usage import (
    TraceCollector,
    append_trace,
    question_candidates,
    read_traces,
    summarize,
)
from ts_knowledge_agent.services.evaluation import (
    DEFAULT_EVALUATION_INTERVAL_MINUTES,
    append_evaluation_run,
    evaluate_citations,
    evaluate_retrieval,
    is_evaluation_due,
    load_cases,
    write_evaluation_report,
)
from ts_knowledge_agent.services.service_control import (
    DEFAULT_WEB_PORT,
    restart_service,
    service_status,
    start_service,
    stop_service,
)
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
    init.add_argument("--skip-scheduled-tasks", action="store_true")

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
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--per-type", type=int, default=6)
    inspect.add_argument("--if-due", action="store_true", help="距上次巡检达到间隔时才执行")
    inspect.add_argument("--interval-minutes", type=int, default=DEFAULT_INSPECTION_INTERVAL_MINUTES)
    inspect.add_argument("--json", action="store_true")
    usage = sub.add_parser("usage")
    usage.add_argument("--days", type=int, default=7)
    usage.add_argument("--suggest", action="store_true", help="输出评测题候选")
    usage.add_argument("--json", action="store_true")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--question-set", type=Path, default=None)
    evaluate.add_argument("--mode", choices=("retrieval", "citations", "both"), default="both")
    evaluate.add_argument("--limit", type=int, default=10)
    evaluate.add_argument("--max-steps", type=int, default=None)
    evaluate.add_argument("--publish", action="store_true", help="把评测报告发布到共享仓治理目录")
    evaluate.add_argument("--if-due", action="store_true", help="距上次评测达到间隔时才执行")
    evaluate.add_argument("--interval-minutes", type=int, default=DEFAULT_EVALUATION_INTERVAL_MINUTES)
    service = sub.add_parser("service")
    service.add_argument("--port", type=int, default=DEFAULT_WEB_PORT)
    service_sub = service.add_subparsers(dest="service_action")
    for action_name in ("start", "stop", "restart", "status"):
        service_sub.add_parser(action_name)
    inspect.add_argument("--no-publish", action="store_true", help="只写本机报告，不写入共享仓治理目录")
    schemas = sub.add_parser("schemas")
    schemas.add_argument("--output", required=True, type=Path)

    return parser


def _install_scheduled_tasks(config_path: Path) -> None:
    """Windows 上注册/刷新启动器与计划任务；非 Windows 或失败时给出明确提示。"""

    if platform.system() != "Windows":
        print("scheduled tasks skipped: windows only")
        return
    script = Path(__file__).resolve().parents[3] / "scripts" / "install-windows-tasks.ps1"
    if not script.is_file():
        print(f"scheduled task installer missing: {script}")
        return
    environment = {**os.environ, "TS_KB_CONFIG": str(config_path)}
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, env=environment,
    )
    for line in (result.stdout or "").strip().splitlines()[-3:]:
        print(line)
    if result.returncode != 0:
        print(f"scheduled task install failed; rerun manually: {script}")


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
        space = ensure_member_space(
            settings.shared_knowledge_repository_directory, settings.personal_workspace
        )
        print(f"member_knowledge={space['knowledge']} member_governance={space['governance']}")
        config_path = settings.working_directory / "ts-kb.json"
        if args.skip_model_setup or not sys.stdin.isatty():
            print("model setup skipped; run ts-team-kb config set / config set-key later")
        else:
            configure_model_interactively(settings).write_file(config_path)
        if args.skip_scheduled_tasks:
            print("scheduled tasks skipped; run scripts/install-windows-tasks.ps1 later")
        else:
            _install_scheduled_tasks(config_path)
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
        collector = TraceCollector()
        result = run_agent(settings, args.question, provider, max_steps=max_steps, on_event=collector)
        append_trace(settings.working_directory, collector.to_record(settings.personal_workspace, "cli"))
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
    if args.command == "usage":
        records = read_traces(settings.working_directory, days=args.days)
        summary = summarize(records)
        if args.suggest:
            summary["candidates"] = question_candidates(settings.working_directory)
        if args.json:
            _print(summary)
        else:
            print("traces=" + str(summary.get("traces", 0))
                  + " zero_hit_rate=" + str(summary.get("zero_hit_rate", 0))
                  + " citation_rate=" + str(summary.get("citation_rate", 0))
                  + " avg_steps=" + str(summary.get("avg_steps", 0)))
            for item in summary.get("top_zero_hit_queries", []):
                print("  zero-hit x" + str(item["count"]) + ": " + str(item["query"]))
            for item in summary.get("candidates", []):
                print("  candidate[" + ",".join(item["reasons"]) + "]: " + item["question"][:60])
        return 0

    if args.command == "evaluate":
        question_set = args.question_set or (Path(__file__).resolve().parents[3] / "evaluation" / "knowledge-questions.json")
        cases = load_cases(question_set)
        if getattr(args, "if_due", False) and not is_evaluation_due(settings.working_directory, args.interval_minutes):
            print(f"skipped=not_due interval_minutes={args.interval_minutes}")
            return 0
        payload: dict = {
            "question_set": str(question_set),
            "mode": args.mode,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.mode in ("retrieval", "both"):
            payload["retrieval"] = evaluate_retrieval(settings, cases, limit=args.limit)
        if args.mode in ("citations", "both"):
            provider = create_provider(settings)
            if provider is None:
                print("model provider not configured; citations evaluation skipped")
            else:
                payload["citations"] = evaluate_citations(
                    settings, cases, provider, max_steps=args.max_steps or settings.model_max_steps)
        path = write_evaluation_report(settings.working_directory, payload)
        append_evaluation_run(settings.working_directory, payload)
        if "retrieval" in payload:
            print("retrieval_nl " + json.dumps(payload["retrieval"]["natural_language"], ensure_ascii=False))
            if payload["retrieval"]["keywords"]:
                print("retrieval_kw " + json.dumps(payload["retrieval"]["keywords"], ensure_ascii=False))
        if "citations" in payload:
            summary = {key: value for key, value in payload["citations"].items() if key != "results"}
            print("citations " + json.dumps(summary, ensure_ascii=False))
        print(f"report={path}")
        if getattr(args, "publish", False):
            published = publish_evaluation_report(
                settings.shared_knowledge_repository_directory, settings.personal_workspace, payload)
            print(f"governance={published}")
        return 0

    if args.command == "service":
        action = getattr(args, "service_action", None)
        service_config = Path(os.getenv("TS_KB_CONFIG", str(settings.working_directory / "ts-kb.json")))
        if action is None:
            parser.error("service requires an action: start | stop | restart | status")
        if action == "status":
            _print(service_status(args.port).to_dict())
            return 0
        if action == "start":
            ok, detail = start_service(settings, config_path=service_config, port=args.port)
        elif action == "stop":
            ok, detail = stop_service(args.port)
        else:
            ok, detail = restart_service(settings, config_path=service_config, port=args.port)
        print(f"{action}: {'ok' if ok else 'failed'} {detail}")
        return 0 if ok else 1

    if args.command == "inspect":
        if args.if_due and not is_inspection_due(settings.working_directory, args.interval_minutes):
            print(f"skipped=not_due interval_minutes={args.interval_minutes}")
            return 0
        started_at = datetime.now(timezone.utc).isoformat()
        report = inspect_knowledge_base(settings, per_type=args.per_type)
        append_inspection_run(settings.working_directory, report, started_at)
        path = write_inspection_report(settings.working_directory, report)
        payload = report.to_dict()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"sampled={report.sampled} clean={report.clean} blocking={report.blocking}")
            for kind, count in report.issue_counts.items():
                print(f"  {kind}: {count}")
            print(f"report={path}")
        if not args.no_publish:
            published = publish_inspection_report(
                settings.shared_knowledge_repository_directory,
                settings.personal_workspace,
                payload,
            )
            if not args.json:
                print(f"governance={published}")
        return 1 if report.blocking else 0
    if args.command == "schemas":
        for path in write_schema_files(args.output):
            print(path)
        return 0

    parser.print_help()
    return 0
