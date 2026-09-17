# 飞书 wiki → Markdown 导出（TS 子树 → TS-Share）

把飞书 wiki 里**指定节点子树**的文档定期导出为 Markdown（含图片），落到团队源目录，
供知识流水线采集、转换、入库与共享。

## 边界与落点

```text
导出范围   wiki 节点「TS」（node_token EcJYwv76NisdK1kY1W0czzBbnoN）
           —— 只导这棵子树；该节点的空间 space_id 7527996824649564162
落点       D:\2Work\Knowledge\TS-Share\飞书导出\<一级分类>\<文档标题>.md
           图片/附件：同目录下 <文档标题>.assets\asset-NN.<ext>
布局       两级（一级分类 + 文档标题）。**不要改回深层嵌套**：实测深层布局下
           递归枚举与逐路径可见性会不一致（六种枚举方式只能看到 28/54），两级布局下六种方式完全一致
不支持     多维表格（bitable）无法转 Markdown —— 扫描时单列报告，不静默丢弃
```

## 运行方式

```text
跑在哪     mos（lark-cli 通过 Volta 的 node 入口调用，user 身份）
定时       每天 07:30（Hermes 定时任务「飞书 wiki 导出（TS 子树 → TS-Share）」）
           无变化 → 静默；有新增/更新或失败 → 推日志群
手动       mos 上执行：
             D:\2Work\Private\Projects\ts-team-knowledge-agent\.venv\Scripts\python.exe ^
               C:\Users\86795\AppData\Local\hermes\scripts\feishu-export-run.py            （增量）
               ... feishu-export-run.py "<标题关键词>"                                      （只导某篇）
备用       mis 上保留同一套脚本与一个**已暂停**的定时任务（链路慢或 mos 异常时启用）
```

## 幂等与停用语义

```text
幂等      按 obj_token + 内容哈希判重；未变化不重写文件（保留 mtime）
          文档改了 → 重导并覆盖**导出的那一份**（它是生成物，不是你手动放的源文件）
停用      文档被移出子树/删除 → **不自动删本地导出**（遵守删除红线），只在报告里列出待人工确认
同名      同一分类下标题重复时，用 obj_token 前 6 位加后缀，避免互相覆盖
溯源      每篇文件头写入：来源链接、node_token、obj_token、导出时间
```

## 已实测的关键坑

```text
1. 图片不能走 drive +download（对图片 token 返回 HTTP 403）→ 改用 drive +preview --type source_file
2. CLI 拒绝把媒体写到**含中文或空格**的输出路径（unsafe output path）
   → 先下到纯 ASCII 临时目录，再由脚本搬运到目标目录
3. 图片链接有两种形式（https://feishu.cn/file/<token> 与 https://<租户>.feishu.cn/file/<token>）
   → 正则要同时覆盖，且不要依赖 alt 文本（alt 里含各种标点）
4. 目录层级别做深：见「布局」一节
5. Windows 控制台是 GBK：任何打印不可表示字符（emoji 等）都会让进程崩溃
   → 打印前降级 errors，别改成 UTF-8（中文会反而变乱码）
```

## 端到端验收（缺一不可）

```text
① 导出：trace 记录数 == 逐路径 is_file 数 == os.walk == scandir == rglob == cmd dir（必须相等）
② 扫描：scan_directory 的结果里，导出文件的 supported 计数 == 导出篇数
③ 登记：跑完转换后，registries/<成员>/sources.jsonl 里出现对应条目，知识仓出现对应 md
```

## 维护入口

```text
应用仓脚本   scripts/feishu-wiki-export.py     ← 唯一源（mos 上的运行副本由它部署）
运行封装     <mos Hermes home>\scripts\feishu-export-run.py（设 CLI 前缀 + 打印约定）
日志         <mos Hermes home>\state\feishu-export.log（每轮一行：exit/new/updated/images/failed）
```
