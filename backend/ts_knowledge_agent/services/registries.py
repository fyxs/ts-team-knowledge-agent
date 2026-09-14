from __future__ import annotations

import json
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.schemas import KnowledgeEntry, ReviewRecord, SourceRegistration


def member_root(settings: Settings) -> Path:
    return settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace


def _write_jsonl(path: Path, records: list) -> int:
    lines = [
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for record in records
    ]
    content = "".join(line + "\n" for line in lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return len(records)
    path.write_text(content, encoding="utf-8")
    return len(records)


def _converter_parts(converter_version: str) -> tuple[str, str]:
    name, _, version = converter_version.partition("-")
    return (name or converter_version), (version or converter_version)


def source_registrations(settings: Settings) -> list[SourceRegistration]:
    repo = settings.shared_knowledge_repository_directory
    store = StateStore(repo / "data" / "state.sqlite3")
    try:
        sizes = {row["relative_path"]: row["size"] for row in store.list_sources()}
        records: list[SourceRegistration] = []
        for row in store.list_conversions():
            if row["relative_path"] not in sizes:
                continue
            output = Path(row["output_path"])
            try:
                knowledge_path = output.relative_to(repo).as_posix()
            except ValueError:
                continue
            converter, version = _converter_parts(row["converter_version"])
            records.append(
                SourceRegistration(
                    member=settings.personal_workspace,
                    source_relative_path=row["relative_path"],
                    source_sha256=row["source_sha256"],
                    source_bytes=sizes[row["relative_path"]],
                    knowledge_path=knowledge_path,
                    converter=converter,
                    converter_version=version,
                    status=row["status"],
                    converted_at=str(row["updated_at"]),
                )
            )
        return sorted(records, key=lambda record: record.source_relative_path)
    finally:
        store.close()


def write_source_registry(settings: Settings) -> int:
    return _write_jsonl(member_root(settings) / "sources.jsonl", source_registrations(settings))


def knowledge_entries(settings: Settings) -> list[KnowledgeEntry]:
    repo = settings.shared_knowledge_repository_directory
    root = member_root(settings)
    if not root.is_dir():
        return []
    by_knowledge_path = {}
    for record in source_registrations(settings):
        if record.status == "converted":
            by_knowledge_path[record.knowledge_path] = record
    entries: list[KnowledgeEntry] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(repo).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        title = next(
            (line[2:].strip() for line in content.splitlines() if line.startswith("# ")),
            path.stem,
        )
        images = path.parent / "images"
        registration = by_knowledge_path.get(relative)
        entries.append(
            KnowledgeEntry(
                member=settings.personal_workspace,
                path=relative,
                title=title,
                markdown_bytes=path.stat().st_size,
                image_count=len([item for item in images.iterdir()]) if images.is_dir() else 0,
                source_sha256=registration.source_sha256 if registration else "",
                converted_at=registration.converted_at if registration else "",
            )
        )
    return entries


def write_knowledge_registry(settings: Settings) -> int:
    return _write_jsonl(member_root(settings) / "knowledge.jsonl", knowledge_entries(settings))


def export_review_records(settings: Settings) -> int:
    repo = settings.shared_knowledge_repository_directory
    source = settings.working_directory / "feedback" / "records.jsonl"
    if not source.is_file():
        return 0
    records: list[ReviewRecord] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        output = str(data.get("output_path", ""))
        knowledge_path = ""
        if output:
            try:
                knowledge_path = Path(output).relative_to(repo).as_posix()
            except ValueError:
                knowledge_path = ""
        records.append(
            ReviewRecord(
                member=settings.personal_workspace,
                knowledge_path=knowledge_path,
                source_sha256=str(data.get("source_sha256", "")),
                issue_category=str(data.get("issue_category", "")),
                observed_issue=str(data.get("observed_issue", "")),
                expected_result=str(data.get("expected_result", "")),
                resolution_status=str(data.get("resolution_status", "open")),
                created_at=str(data.get("created_at", "")),
            )
        )
    return _write_jsonl(member_root(settings) / "reviews.jsonl", records)
