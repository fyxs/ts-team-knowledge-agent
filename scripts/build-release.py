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
import zipfile
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




UV_VERSION = "0.12.15"
UV_ASSET = "uv-x86_64-pc-windows-msvc.zip"


def ensure_bundled_uv(bundle: Path, out_dir: Path, version: str = UV_VERSION) -> Path:
    """把 uv.exe 放进免安装包的 tools/ 目录。

    这样即使目标机器上既没有 Python 也没有 uv，setup-mineru 也能一步制备 MinerU，
    不需要成员先自行安装任何东西。

    来源优先 PyPI（与运行时同一分发通道，实测稳定且带缓存），GitHub Release 作为兜底。
    """

    import urllib.request

    target = bundle / "tools" / "uv.exe"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    cache = PROJECT_ROOT / ".cache" / "uv-bundle"
    cache.mkdir(parents=True, exist_ok=True)

    # 路线一：PyPI 上的 uv wheel 里就有 uv.exe（*.data/scripts/uv.exe）
    result = subprocess.run([sys.executable, "-m", "pip", "download", "uv", "--no-deps", "--only-binary", ":all:",
                             "-d", str(cache)], capture_output=True, text=True)
    if result.returncode == 0:
        wheels = sorted(cache.glob("uv-*.whl"))
        if wheels:
            with zipfile.ZipFile(wheels[-1]) as handle:
                member = next((name for name in handle.namelist() if name.lower().endswith("scripts/uv.exe")), None)
                if member is None:
                    member = next((name for name in handle.namelist() if name.lower().endswith("uv.exe")), None)
                if member is not None:
                    target.write_bytes(handle.read(member))
                    return target

    # 路线二：GitHub Release 资源
    archive = cache / f"uv-{version}-{UV_ASSET}"
    if not archive.exists():
        url = f"https://github.com/astral-sh/uv/releases/download/{version}/{UV_ASSET}"
        print(f"uv: 从 GitHub 下载 {url}")
        with urllib.request.urlopen(url, timeout=900) as response:
            archive.write_bytes(response.read())
    with zipfile.ZipFile(archive) as handle:
        member = next(name for name in handle.namelist() if name.lower().endswith("uv.exe"))
        target.write_bytes(handle.read(member))
    return target



def write_bundle_readme(bundle: Path) -> Path:
    """把使用说明放进免安装包：解压即可看到，不用另外发文档。

    写成 UTF-8 BOM + CRLF —— Windows 记事本双击打开不会乱码、不会挤成一行。
    """

    template = PROJECT_ROOT / "packaging" / "bundle-readme.txt"
    if not template.is_file():
        raise SystemExit(f"缺少说明模板：{template}")
    body = template.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    target = bundle / "使用说明.txt"
    target.write_text(body, encoding="utf-8-sig")
    return target


def build_bundle(out_dir: Path, build_python: Path | None = None, *, bundle_uv: bool = True,
                 clean_intermediates: bool = True) -> Path:
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
    write_bundle_readme(bundle)
    if bundle_uv:
        uv_path = ensure_bundled_uv(bundle, out_dir)
        print(f'bundled_uv={uv_path} bytes={uv_path.stat().st_size}')
    version = _project_version()
    archive = out_dir / f"ts-team-kb-{version}-win-x64.zip"
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
        for path in bundle.rglob('*'):
            if path.is_file():
                handle.write(path, Path('ts-team-kb') / path.relative_to(bundle))
    if clean_intermediates:
        for stale in (out_dir / 'pyi-work', target):
            if stale.exists():
                shutil.rmtree(stale, ignore_errors=True)
        print('intermediates cleaned: pyi-work/, packaging/')
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
    parser.add_argument("--no-bundle-uv", action="store_true", help="不把 uv.exe 打进免安装包")
    parser.add_argument("--keep-intermediates", action="store_true", help="保留 PyInstaller 中间物（默认构建后清理）")
    args = parser.parse_args()
    wheel = build(Path(args.out))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    print(f"wheel={wheel}")
    print(f"bytes={wheel.stat().st_size}")
    print(f"sha256={digest}")
    if args.exe:
        archive = build_bundle(Path(args.out), Path(args.build_python) if args.build_python else None,
                               bundle_uv=not args.no_bundle_uv,
                           clean_intermediates=not args.keep_intermediates)
        print(f"zip={archive}")
        print(f"zip_bytes={archive.stat().st_size}")
        print(f"zip_sha256={hashlib.sha256(archive.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
