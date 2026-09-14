from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class SourceRegistration(BaseModel):
    """来源登记：一条源文件到知识结果的登记。"""

    member: str = Field(description="成员空间标识")
    source_relative_path: str = Field(description="共享源目录内的相对路径")
    source_sha256: str = Field(description="源文件内容哈希")
    source_bytes: int | None = Field(default=None, description="源文件大小（字节）")
    knowledge_path: str = Field(description="知识仓内相对路径，使用 POSIX 分隔符")
    converter: str = Field(description="转换器名称")
    converter_version: str = Field(description="转换器版本")
    status: str = Field(description="转换状态：converted / quality_failed / blocked_secret / failed_retryable")
    converted_at: str = Field(description="最近一次转换时间（UTC ISO8601）")


class KnowledgeEntry(BaseModel):
    """知识条目：知识仓内一份可被 Agent 读取的 Markdown 及其来源。"""

    member: str = Field(description="成员空间标识")
    path: str = Field(description="知识仓内相对路径，使用 POSIX 分隔符")
    title: str = Field(description="文档标题")
    markdown_bytes: int = Field(description="Markdown 文件大小（字节）")
    image_count: int = Field(description="同目录 images/ 下的图片数量")
    source_sha256: str = Field(description="对应源文件内容哈希；无登记时为空字符串")
    converted_at: str = Field(description="来源登记的转换时间；无登记时为空字符串")


class ReviewRecord(BaseModel):
    """审查记录：对某份知识条目的人工或 Agent 审查与反馈。"""

    member: str = Field(description="成员空间标识")
    knowledge_path: str = Field(description="知识仓内相对路径；无法确定时为空字符串")
    source_sha256: str = Field(description="对应源文件内容哈希")
    issue_category: str = Field(description="问题分类")
    observed_issue: str = Field(description="实际观察到的现象")
    expected_result: str = Field(description="期望结果")
    resolution_status: str = Field(description="处理状态：open / confirmed / fixed / wont_fix")
    created_at: str = Field(description="记录时间（UTC ISO8601）")


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "knowledge-entry": KnowledgeEntry,
    "source-registration": SourceRegistration,
    "review-record": ReviewRecord,
}


def write_schema_files(target: Path) -> list[Path]:
    """把三个工件格式写成 JSON Schema 文件，供知识仓 schemas/ 使用。"""

    target = target.expanduser()
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in sorted(SCHEMA_MODELS.items()):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = name
        path = target / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written
