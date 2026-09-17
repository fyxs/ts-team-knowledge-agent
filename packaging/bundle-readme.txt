TS 团队知识 Agent · 免安装版使用说明
=====================================

【这个包里是什么】
  ts-team-kb.exe        主程序（已内置 Python 运行时，无需另装）
  tools\uv.exe          Python 环境管理器（机器上没有 Python 时由它自动准备）
  _internal\...         程序依赖与网页界面资源（无需 Node）

【需要什么】
  Windows 10 / 11 64 位；磁盘预留约 1.5 GB（其中转换引擎约 1.1 GB）
  不需要预装 Python、Node 或 uv

【快速开始（四步）】
  1. 解压到任意目录，例如 D:\ts-team-kb

  2. 制备转换环境（首次约 5-15 分钟，需联网；会下载约 1.1 GB）
        ts-team-kb.exe setup-mineru
     看到 pipeline-ok 表示转换能力已就绪。

  3. 初始化（会依次询问：模型供应商 / 请求地址 / API Key / 模型名）
        ts-team-kb.exe init --working-directory D:\2Work\Knowledge\kb-shared-workspace ^
                            --personal-workspace <你的成员标识> ^
                            --shared-source-directory D:\2Work\Knowledge\TS-Share

  4. 注册后台任务并启动界面
        ts-team-kb.exe service install
        ts-team-kb.exe serve --host 0.0.0.0 --port 8088
     浏览器打开 http://127.0.0.1:8088

【常用命令】
  ts-team-kb.exe --help                                 查看全部命令
  ts-team-kb.exe status                                 查看状态
  ts-team-kb.exe scan --if-due                          扫描一次（按间隔判断是否需要跑）
  ts-team-kb.exe ask "BFF 项目新起要改哪些配置？"          命令行问答
  ts-team-kb.exe convert --file a.pdf --output a.md     单文件转换
  ts-team-kb.exe inspect                                知识库质量巡检
  ts-team-kb.exe setup-mineru --python <解释器>          复用已有的转换环境

【常见问题】
  · setup-mineru 很慢或看起来卡住
    首次要下载约 1.1 GB 依赖与模型，属正常；中断后重跑会复用已下载内容。
  · 提示找不到 Python
    不需要自己装：包内 tools\uv.exe 会自动准备。若提示找不到引导解释器，
    请确认 tools\uv.exe 存在（部分杀毒软件会隔离它）。
  · 界面打不开
    确认 8088 端口没被占用：netstat -ano | findstr 8088；也可换端口启动。
  · 转换时报缺少模块
    重跑 ts-team-kb.exe setup-mineru（会补齐转换引擎未声明的依赖）。
  · 日志在哪
    <工作目录>\logs\：serve.log、scheduled-run.log、runner-errors.log。

【卸载】
  停掉计划任务与进程后，删除整个目录即可。工作目录里的数据请自行处理。

【安全说明】
  知识源目录是只读的：程序不会移动、覆盖、重命名或删除你的原始文件。
  API Key 保存在 <工作目录>\secrets\model.key，不进入任何仓库。

【非交互安装（脚本 / 批量部署）】
  一次装完，不需要在 init 时回答交互问题：
    ts-team-kb.exe init --working-directory D:\2Work\Knowledge\kb-shared-workspace ^
                        --personal-workspace <成员标识> ^
                        --shared-source-directory D:\2Work\Knowledge\TS-Share ^
                        --provider ts_proxy --model <模型名> --base-url <接口地址>
  密钥单独写（不要放进命令行，会进历史记录和日志）：
    ts-team-kb.exe config set-key --from-file <密钥文件>

【让服务在后台静默运行（不要留黑窗）】
  推荐用 service install 注册计划任务，由系统隐藏启动：
    ts-team-kb.exe service install
  不要把 `ts-team-kb.exe serve` 的窗口长期挂着；前台启动只用于临时排查。

【配置文件位置（报"找不到配置"时看这里）】
  命令按以下顺序查找 ts-kb.json：
    1) 环境变量 TS_KB_CONFIG 指定的路径
    2) 当前目录下的 ts-kb.json
    3) 当前目录下的 .local\ts-kb.json
    4) 环境变量 TS_KB_WORKING_DIRECTORY 目录下的 ts-kb.json
  所以要么 cd 到工作目录再执行命令，要么显式设置 TS_KB_CONFIG。
  重跑 init 不会丢配置：只更新 working-directory / personal-workspace /
  shared-source-directory / scan-interval-minutes / shared-knowledge-repository-url，
  模型设置、mineru_python、excluded_source_paths、sources_* 等原样保留。

【复用已有转换环境，不重复下载约 1.1 GB】
    ts-team-kb.exe config set --mineru-python <已有 MinerU 的 python.exe 路径>
  安装时也可以：ts-team-kb.exe setup-mineru --python <同一路径>
