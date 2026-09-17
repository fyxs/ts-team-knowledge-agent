"""PyInstaller 入口：启动 ts-team-kb 命令行。"""

import multiprocessing
import sys

from ts_knowledge_agent.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main(sys.argv[1:]))
