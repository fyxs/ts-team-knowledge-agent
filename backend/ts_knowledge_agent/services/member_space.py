"""成员空间：个人知识目录与治理记录目录的定位与初始化。

边界：
- `members/<成员>/` 只存放该成员共享的知识，参与检索与登记表生成。
- `governance/<成员>/` 存放巡检与治理留痕，不参与知识检索与登记表生成。
两者在初始化时一次性建好，互不交叉。
"""

from __future__ import annotations

from pathlib import Path

MEMBERS_DIRECTORY = "members"
GOVERNANCE_DIRECTORY = "governance"
INSPECTION_SUBDIRECTORY = "inspection"
KEEP_INSPECTION_REPORTS = 30

MEMBER_README_TEXT = """# 个人知识空间（{member}）

本目录只存放该成员共享的知识文档。

- 内容来自本机源材料的转换结果，进入仓库即默认团队共享
- 检索与登记表只覆盖本目录
- 治理与巡检记录不放在这里，见 `governance/{member}/`
"""

GOVERNANCE_README_TEXT = """# 治理记录（governance）

本目录存放各成员的检查与治理留痕，**不是知识内容**。

- 按成员划分：`governance/<成员>/`
- 个人知识空间 `members/<成员>/` 只存放该成员共享的知识，两者不交叉
- 内容由应用写入，不要手工编辑

三类产物（均由应用自动写入并随知识仓同步提交）：

| 子目录 | 内容 | 产生者 |
| --- | --- | --- |
| `inspection/` | 知识库质量巡检报告 | `ts-team-kb inspect` |
| `evaluation/` | 检索与引用质量评测报告 | `ts-team-kb evaluate` |
| `usage/` | 使用埋点按日汇总（检索链路） | 随扫描轮次自动汇总 |

保留策略：巡检与评测报告各保留最近 {keep} 份，超出后自动清理最早的；
使用埋点长期保留（体积过大时压缩而非删除）。

约定：

- 本目录不参与知识检索与登记表生成（检索只覆盖 `members/`）
- 本目录内容随知识仓同步提交，供团队成员查看运行健康度
"""


GOVERNANCE_MEMBER_README_TEXT = """# 治理记录（{member}）

本目录存放 **{member}** 这个成员的检查与治理留痕，不是知识内容。

- 归属：只记录该成员本机的运行与质量数据；其他成员的记录在各自的目录下
- 内容由应用写入（巡检 / 评测 / 埋点汇总），不要手工编辑
- 目录级说明见上一层 `governance/README.md`

"""

def _member_name(member: str) -> str:
    name = (member or "").strip()
    if not name:
        raise ValueError("member must not be empty")
    return name


def member_knowledge_directory(repository_root: Path, member: str) -> Path:
    """返回某个成员在共享仓中的个人知识目录。"""

    return Path(repository_root) / MEMBERS_DIRECTORY / _member_name(member)


def member_governance_directory(repository_root: Path, member: str) -> Path:
    """返回某个成员在共享仓中的治理记录目录。"""

    return Path(repository_root) / GOVERNANCE_DIRECTORY / _member_name(member)


def is_knowledge_document(relative_posix: str) -> bool:
    """判断仓库内相对路径是否为知识文档：空间说明用 README 不算知识。"""

    if relative_posix == "members/README.md":
        return False
    parts = relative_posix.split("/")
    if len(parts) == 3 and parts[0] == MEMBERS_DIRECTORY and parts[2] == "README.md":
        return False
    return True


def _write_readme(directory: Path, text: str, *, rewrite_legacy: str | None = None) -> None:
    """写入目录说明。默认不覆盖已存在的文件；传 rewrite_legacy 时，
    若现有内容包含该标记（历史错位文本），则按当前模板修正。"""

    readme = directory / "README.md"
    if readme.is_file():
        if rewrite_legacy is None:
            return
        try:
            current = readme.read_text(encoding="utf-8")
        except OSError:
            return
        if rewrite_legacy not in current:
            return
    readme.write_text(text, encoding="utf-8", newline="\n")


def ensure_member_space(repository_root: Path, member: str) -> dict[str, Path]:
    """初始化成员空间：个人知识目录与治理记录目录（幂等）。"""

    name = _member_name(member)
    knowledge = member_knowledge_directory(repository_root, name)
    knowledge.mkdir(parents=True, exist_ok=True)
    _write_readme(knowledge, MEMBER_README_TEXT.format(member=name))

    governance_root = Path(repository_root) / GOVERNANCE_DIRECTORY
    governance_root.mkdir(parents=True, exist_ok=True)
    _write_readme(governance_root, GOVERNANCE_README_TEXT.format(keep=KEEP_INSPECTION_REPORTS))

    governance = member_governance_directory(repository_root, name)
    governance.mkdir(parents=True, exist_ok=True)
    # 历史版本把目录级说明写进了成员目录，这里按标记修正为成员级说明
    _write_readme(
        governance,
        GOVERNANCE_MEMBER_README_TEXT.format(member=name),
        rewrite_legacy="按成员划分：`governance/<成员>/`",
    )
    return {"knowledge": knowledge, "governance": governance, "governance_root": governance_root}
