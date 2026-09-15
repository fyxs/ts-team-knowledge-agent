"""构建发布产物：在临时目录打包，避免污染仓库工作区。

用法：python scripts/build-release.py [--out <目录>]
产物：dist-release/<wheel> 与校验信息（后续 exe/zip 也走这里）
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDES = {".git", ".venv", "node_modules", "dist-release", "__pycache__", ".pytest_cache", "logs"}


def copy_tree(source: Path, target: Path) -> None:
    """复制源码树，跳过虚拟环境、依赖与构建产物。"""

    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in EXCLUDES:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, ignore=shutil.ignore_patterns(*EXCLUDES))
        else:
            shutil.copy2(item, destination)


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if not (frontend_dist / "index.html").is_file():
        raise SystemExit("前端产物缺失：请先构建 frontend/dist（发布包必须自带前端）")
    with tempfile.TemporaryDirectory(prefix="ts-kb-build-") as workspace:
        staging = Path(workspace) / "src"
        copy_tree(PROJECT_ROOT, staging)
        # 前端产物放进包内（发布安装不依赖 Node）
        packaged_web = staging / "backend" / "ts_knowledge_agent" / "web"
        shutil.copytree(frontend_dist, packaged_web)
        command = [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(out_dir)]
        result = subprocess.run(command, cwd=str(staging), capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout[-2000:])
            print(result.stderr[-2000:])
            raise SystemExit(f"构建失败，退出码 {result.returncode}")
    wheels = sorted(out_dir.glob("*.whl"))
    if not wheels:
        raise SystemExit("未生成 wheel")
    return wheels[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PROJECT_ROOT / "dist-release"))
    args = parser.parse_args()
    wheel = build(Path(args.out))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    print(f"wheel={wheel}")
    print(f"bytes={wheel.stat().st_size}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
