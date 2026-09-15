"""构建发布产物：在临时目录打包，避免污染仓库工作区。

用法：python scripts/build-release.py [--out <目录>]
产物：dist-release/<wheel> 与校验信息（后续 exe/zip 也走这里）
"""

from __future__ import annotations

import argparse
import hashlib
import os
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



def build_bundle(out_dir: Path, build_python: Path | None = None) -> Path:
    """用 PyInstaller 产出免安装目录，并打成 zip（exe 分发件）。"""

    import zipfile

    interpreter = build_python or Path(sys.executable)
    check = subprocess.run([str(interpreter), '-c', 'import PyInstaller'], capture_output=True, text=True)
    if check.returncode != 0:
        raise SystemExit(f"该解释器没有 PyInstaller：{interpreter}；请先 pip install -e .[build]")
    target = out_dir / 'packaging'
    target.mkdir(parents=True, exist_ok=True)
    # 暂存源码树与前端产物：让打包用的是"当前源码"，不是构建环境里的旧安装
    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if not (frontend_dist / "index.html").is_file():
        raise SystemExit("前端产物缺失：发布包必须自带前端（先构建 frontend/dist）")
    staging_root = Path(tempfile.mkdtemp(prefix="ts-kb-exe-"))
    staging_backend = staging_root / "backend"
    copy_tree(PROJECT_ROOT / "backend", staging_backend)
    staging_web = staging_root / "web"
    shutil.copytree(frontend_dist, staging_web)
    build_env = dict(os.environ)
    build_env["TS_KB_BUILD_BACKEND"] = str(staging_backend)
    build_env["TS_KB_BUILD_WEB"] = str(staging_web)
    result = subprocess.run(
        [str(interpreter), '-m', 'PyInstaller', str(PROJECT_ROOT / 'packaging' / 'ts-team-kb.spec'),
         '--noconfirm', '--clean', '--distpath', str(target), '--workpath', str(out_dir / 'pyi-work')],
        cwd=str(PROJECT_ROOT / 'packaging'), capture_output=True, text=True, env=build_env)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise SystemExit("PyInstaller 构建失败")
    bundle = target / 'ts-team-kb'
    version = _project_version()
    archive = out_dir / f"ts-team-kb-{version}-win-x64.zip"
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
        for path in bundle.rglob('*'):
            if path.is_file():
                handle.write(path, Path('ts-team-kb') / path.relative_to(bundle))
    return archive


def _project_version() -> str:
    """从 pyproject 读版本号，保证产物名与包版本一致。"""

    for line in (PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8').splitlines():
        if line.startswith('version'):
            return line.split('=')[1].strip().strip('"')
    return '0.0.0'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PROJECT_ROOT / "dist-release"))
    parser.add_argument("--exe", action="store_true", help="同时构建免安装目录并打包 zip")
    parser.add_argument("--build-python", default=None, help="含 PyInstaller 的解释器路径")
    args = parser.parse_args()
    wheel = build(Path(args.out))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    print(f"wheel={wheel}")
    print(f"bytes={wheel.stat().st_size}")
    print(f"sha256={digest}")
    if args.exe:
        archive = build_bundle(Path(args.out), Path(args.build_python) if args.build_python else None)
        print(f"zip={archive}")
        print(f"zip_bytes={archive.stat().st_size}")
        print(f"zip_sha256={hashlib.sha256(archive.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
