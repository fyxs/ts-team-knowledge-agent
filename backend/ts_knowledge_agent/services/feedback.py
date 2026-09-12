from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class FeedbackRecord:
    source_relative_path: str
    source_sha256: str
    file_type: str
    converter: str
    converter_version: str
    output_path: str
    category: str
    description: str
    expected: str
    source_issue: bool
    adapter_issue: bool
    resolution: str
    review_status: str

    def validate(self) -> None:
        if len(self.source_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.source_sha256.lower()):
            raise ValueError("source_sha256 must be a 64-character hexadecimal SHA-256")
        if not self.source_relative_path:
            raise ValueError("source_relative_path must not be empty")
        if not self.category:
            raise ValueError("category must not be empty")
        if not self.description:
            raise ValueError("description must not be empty")
        if not self.review_status:
            raise ValueError("review_status must not be empty")


def _feedback_path(working_directory: Path) -> Path:
    return working_directory / "feedback" / "records.jsonl"


def append_feedback(working_directory: Path, record: FeedbackRecord) -> Path:
    record.validate()
    path = _feedback_path(working_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return path


def list_feedback(working_directory: Path) -> list[FeedbackRecord]:
    path = _feedback_path(working_directory)
    if not path.is_file():
        return []
    records: list[FeedbackRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = FeedbackRecord(**json.loads(line))
            record.validate()
            records.append(record)
    return records
