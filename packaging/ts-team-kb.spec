# PyInstaller 打包配置：产出免安装的 ts-team-kb 目录（folder 模式，避免 onefile 被误报）。
# MinerU 及其重依赖（torch/transformers 等）在进程内从不 import（转换走独立解释器），
# 因此这里显式排除，由首次运行或安装器单独制备。

import os

from PyInstaller.utils.hooks import collect_submodules

hidden = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "anyio._backends._asyncio",
]
hidden += collect_submodules("ts_knowledge_agent")

excludes = [
    "mineru", "mineru_vl_utils", "torch", "torchvision", "transformers", "opencv", "cv2",
    "modelscope", "gradio", "matplotlib", "pandas", "scipy", "tkinter", "PyQt5", "pytest",
]

a = Analysis(
    ["entry.py"],
    # 关键：显式指向当前源码树，否则 PyInstaller 会从构建环境 site-packages 取
    # 已安装的旧包，导致发布件里是陈旧代码（曾因此让 exe 缺少新命令）。
    pathex=[os.environ.get("TS_KB_BUILD_BACKEND", "")],
    hiddenimports=hidden,
    excludes=excludes,
    # 前端产物随包分发：成员机无需 Node（由构建脚本指定路径）
    datas=[(os.environ.get("TS_KB_BUILD_WEB", ""), "ts_knowledge_agent/web")],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ts-team-kb",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ts-team-kb")
