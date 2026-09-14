from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class SourceRegistration(BaseModel):
    """来源登记：一条源文件到知识结果的登记。"""

    member: str = Field(description="成员空间标识")
    source_relative_path: str = Field(description="共享源目录内的相对路径")
    source_sha256: str = Field(description="源文件 SHA-256")
    source_bytes: int | None = Field(default=None, description="源文件字节数，未知时为 null")
    knowledge_path: str = Field(description="知识仓内相对路径（POSIX 分隔符），无法确定时为空字符串")
    converter: str = Field(description="转换器名称")
    converter_version: str = Field(description="转换器版本")
    status: str = Field(description="converted / quality_warned / quality_failed / blocked_secret / failed_retryable 等")
    converted_at: str = Field(description="该记录最后更新时间（UTC）")


class KnowledgeEntry(BaseModel):
    """知识条目：仓库内可直接阅读的知识文档。"""

    member: str = Field(description="成员空间标识")
    path: str = Field(description="知识仓内相对路径（POSIX 分隔符）")
    title: str = Field(description="文档标题，取首个一级标题，缺省为文件名")
    markdown_bytes: int = Field(description="Markdown 字节数")
    image_count: int = Field(description="文档目录内 images/ 的图片数量")
    source_sha256: str = Field(description="来源登记中的源文件 SHA-256，未登记时为空字符串")
    converted_at: str = Field(description="来源登记中的转换时间，未登记时为空字符串")


class ReviewRecord(BaseModel):
    """审查记录：对某条知识或某次转换的人工/Agent 审查结论。"""

    member: str = Field(description="成员空间标识")
    knowledge_path: str = Field(description="被审查知识在仓内的相对路径，无法确定时为空字符串")
    source_relative_path: str = Field(description="源文件在共享源目录内的相对路径")
    source_sha256: str = Field(description="源文件 SHA-256，用于定位具体版本")
    file_type: str = Field(description="源文件扩展名")
    category: str = Field(description="问题分类，例如 credential_exposure、missing_content、encoding")
    description: str = Field(description="观察到的问题，不得包含凭据值")
    expected: str = Field(description="期望结果")
    source_issue: bool = Field(description="是否属于源文件本身的问题")
    adapter_issue: bool = Field(description="是否属于转换适配器的问题")
    resolution: str = Field(description="处理结论")
    review_status: str = Field(description="open / resolved 等审查状态")


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "knowledge-entry": KnowledgeEntry,
    "source-registration": SourceRegistration,
    "review-record": ReviewRecord,
}


def write_schema_files(target: Path) -> list[Path]:
    """把模型定义导出为 JSON Schema 文件，保证文档与实现不漂移。"""

    target = target.expanduser().resolve()
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
