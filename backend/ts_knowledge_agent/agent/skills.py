from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: str


def _parse(text: str, path: Path) -> Skill | None:
    name = ""
    description = ""
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            header, body = parts[1], parts[2].lstrip("\n")
            for line in header.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
    name = name or path.stem
    if not description:
        return None
    return Skill(name=name, description=description, body=body.strip(), path=str(path))


def load_skills(directory: Path | None = None) -> list[Skill]:
    target = Path(directory) if directory else DEFAULT_SKILLS_DIR
    if not target.is_dir():
        return []
    skills: list[Skill] = []
    for path in sorted(target.rglob("*.md")):
        skill = _parse(path.read_text(encoding="utf-8"), path)
        if skill is not None:
            skills.append(skill)
    return skills


def find_skill(skills: list[Skill], name: str) -> Skill | None:
    wanted = (name or "").strip().lower()
    for skill in skills:
        if skill.name.lower() == wanted:
            return skill
    return None
