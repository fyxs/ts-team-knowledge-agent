from __future__ import annotations

import json
from pathlib import Path

from ts_knowledge_agent.config import Settings
from ts_knowledge_agent.repositories.state_store import StateStore
from ts_knowledge_agent.schemas import KnowledgeEntry, ReviewRecord, SourceRegistration


def member_root(settings: Settings) -> Path:
    return settings.shared_knowledge_repository_directory / "members" / settings.personal_workspace


def _write_jsonl(path: Path, records: list) -> int:
    lines = [json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) for record in records]
    content = "".join(line + "\n" for line in lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return len(records)
    path.write_text(content, encoding="utf-8")
    return len(records)


def _converter_parts(converter_version: str) -> tuple[str, str]:
    name, separator, version = converter_version.partition("-")
    if not separator:
        return converter_version, ""
    return name, version


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def source_registrations(settings: Settings) -> list[SourceRegistration]:
    repo = settings.shared_knowledge_repository_directory
    store = StateStore(repo / "data" / "state.sqlite3")
    try:
        sizes = {row["relative_path"]: row["size"] for row in store.list_sources()}
        records: list[SourceRegistration] = []
        for row in store.list_conversions():
            converter, version = _converter_parts(row["converter_version"])
            records.append(
                SourceRegistration(
                    member=settings.personal_workspace,
                    source_relative_path=row["relative_path"],
                    source_sha256=row["source_sha256"],
                    source_bytes=sizes.get(row["relative_path"]),
                    knowledge_path=_relative_posix(Path(row["output_path"]), repo),
                    converter=converter,
                    converter_version=version,
                    status=row["status"],
                    converted_at=row["updated_at"],
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
    if not root.exists():
        return []
    registered = {record.knowledge_path: record for record in source_registrations(settings)}
    entries: list[KnowledgeEntry] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(repo).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), path.stem)
        images = path.parent / "images"
        registration = registered.get(relative)
        entries.append(
            KnowledgeEntry(
                member=settings.personal_workspace,
                path=relative,
                title=title,
                markdown_bytes=path.stat().st_size,
                image_count=len([item for item in images.iterdir() if item.is_file()]) if images.is_dir() else 0,
                source_sha256=registration.source_sha256 if registration else "",
                converted_at=registration.converted_at if registration else "",
            )
        )
    return entries


def write_knowledge_registry(settings: Settings) -> int:
    return _write_jsonl(member_root(settings) / "knowledge.jsonl", knowledge_entries(settings))


def export_review_records(settings: Settings) -> int:
    from ts_knowledge_agent.services.feedback import list_feedback

    repo = settings.shared_knowledge_repository_directory
    records: list[ReviewRecord] = []
    for record in list_feedback(settings.working_directory):
        records.append(
            ReviewRecord(
                member=settings.personal_workspace,
                knowledge_path=_relative_posix(Path(record.output_path), repo),
                source_relative_path=record.source_relative_path,
                source_sha256=record.source_sha256,
                file_type=record.file_type,
                category=record.category,
                description=record.description,
                expected=record.expected,
                source_issue=record.source_issue,
                adapter_issue=record.adapter_issue,
                resolution=record.resolution,
                review_status=record.review_status,
            )
        )
    return _write_jsonl(member_root(settings) / "reviews.jsonl", records)
