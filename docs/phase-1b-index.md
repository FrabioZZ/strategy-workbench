# Phase 1B — 社交视频链接导入

协调日期：2026-11-09（Asia/Shanghai）。本阶段复用 `C:/Users/Admin/Desktop/quant`；非 Git 仓库，无 branch、无独立 worktree。

## 范围与接收标准

- 粘贴 B站/抖音单视频 URL 或分享文案，服务端抽取、规范化唯一链接；支持短链、B站分P；拒绝歧义多链接。
- 下载独立于 ASR 配置，缓存媒体并呈现真实音频/视频类型；未配置 ASR 时显示已获取、待转写。
- 支持手动启动/重试转写，复用缓存，保留文本校对、策略提取与导出流程。
- 记录实际元数据与来源，安全中文错误，保留下载限制与实际连接地址检查。
- 采用现有 yt-dlp 独立实现；参考仓库关系见 `research/python-spider-evaluation.md`。不执行或复制其旧脚本，不引入账号抓取、登录绕过、OCR或交易功能。

## 可见工作流

| 工作流 | 聊天名 / ID | 工作目录 / 分支 | 状态 | 验收检查点 |
| --- | --- | --- | --- | --- |
| 协调 | Phase 1B - 社交视频链接导入协调 / `01a1bf39-44f1-7af1-8e61-ded13e3981c7` | 同目录 / 无 | 完成，当前无会话授权范围接受 | 范围、真实平台小样本、运行服务、最终接收 |
| 实现 | Phase 1B - 分享链接与缓存媒体实现 / `01a1bf3d-3c3b-7e32-840c-2f04de194daa` | 同目录 / 无 | 完成，最终69项及浏览器通过 | 后端、前端、回归测试、README |
| 基本验收 | Phase 1B - 链接导入基本验收 / `01a1bf3f-b0f0-7c50-89e3-36e8ac477f10` | 同目录 / 无 | 完成；初始R1由跟进修复关闭 | 69项测试、独立接口及浏览器验证；原发现保留在review报告 |
| 跟进修复 | Phase 1B - 恢复本地媒体播放 / `01a1bf56-3412-76e3-b7d6-7de314cd1896` | 同目录 / 无 | 完成，R1关闭 | 真实WAV/H.264播放、历史证据1秒定位、无损保留；最终78项及Chrome通过 |

## 初始证据与待办

- 旧 `Jobs.run` 在下载前检查 `asr_ready()`，导致无模型时不能获取链接。旧前端仅 URL 输入。
- 正式 `http://127.0.0.1:8765/api/status` 可访问；ASR、AI 均未配置。不能以沙盒中的网络进程枚举空结果断言服务不存在。
- 环境 yt-dlp 版本 `2026.10.26`。真实平台测试将用官方 extractor 公开样例，先元数据、再有界单媒体获取；测试文件保存在独立 `.runtime`，不污染 `data/`。
- 用户后续提供完整抖音分享文案（短链 `https://v.douyin.com/aU0BxZKBvVI/`）。已走真实产品入口，唯一链接抽取正确；短链302→iesdouyin→douyin视频 `7664970443358489856` 200。yt-dlp在媒体元数据阶段要求 fresh cookies，产品显示安全平台限制，尚未取得媒体/可信时长/体积。使用默认200 MB、120分钟上限，非ASR或测试大小上限阻塞。详细证据见 `phase-1b-network.md` 用户实际文案章节；此结论优先于旧公开样例。
- 官方 extractor 样例元数据实测：B站 `BV1bK411W797?p=2` 成功返回 `BV1bK411W797_p2`、97.941秒和9个格式；抖音 `6961737553342991651` 失败，要求 cookies/登录。未读取任何用户cookies；抖音尚未获取媒体。证据 `.runtime/phase1b-network/*-metadata.json`。
- 产品真实路径已测：B站第2P成功缓存2,170,299字节M4A音频，Chrome实际播放，状态已获取待转写，未配置ASR手动入口HTTP409；抖音真实worker返回安全平台限制提示，未下载。见 `phase-1b-network.md` 及 `output/playwright/phase1b-live-result.json`。所有样例存于隔离目录，未写入正式资料库。
- 完成后安全重启本项目8765服务，并捕获页面证据。保留用户已有资料。
- 兼容性验收须覆盖旧版SQLite新增字段迁移后原转写、草案、任务均保留，不能仅验证新库。重启前使用SQLite备份API保存一致性快照。最终浏览器检查使用新标签/独立浏览器，不覆盖用户未保存输入；提醒已有页面刷新以加载新代码。
- 协调独立旧库检查已通过：用 Phase 1 原始建表SQL构建旧库，升级后逐列对比原 documents/jobs/strategies 内容不变，原转写、草案、已完成任务、媒体接口与JSON导出均保留。脚本 `.runtime/phase1b-legacy-check.py`；首次证据目录 `.runtime/phase1b-legacy-169c65e19ac847ca805147dad98866da`。若后续修改迁移逻辑需复跑。
- 协调新鲜验证：`.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1b-coordinator-pytest -p no:cacheprovider --tb=short` 为 **68 passed in 4.82s**；`node --check frontend/app.js` 和 `frontend/api.js` 退出0。
- R1修复后再次独立执行旧库兼容脚本通过：`.runtime/phase1b-legacy-647f485b292843ddb56466cc728f2116`；原documents/jobs/strategies全部旧列与原文/草案/任务/媒体/导出仍保留。
- 原协调提供的后续会话功能建议见 `research/douyin-session-design.md`，**仅设计，未实现且未授权在本阶段扩张**。用户实际样例的fresh cookies是下载器未取得aweme_detail时给出的提示，并非平台已确认Cookie过期或必须账号登录。

## 接收结论

**当前授权的无会话授权版本已完成并接受。** 初次基本验收R1已由 `phase-1b-fix.md` 关闭：实际WAV及H.264播放、历史草案证据跳转到第1秒、旧资料保留均通过。协调复跑全套为 **78 passed in 17.13s**（`.runtime/phase1b-coordinator-final`）；独立旧版原始建表数据库逐列保留检查通过。原验收报告保留历史发现，不覆盖其结论。

### 正式运行与资料保留

- 一致性备份：`.runtime/phase1b-production-backup-9e40e1aa35914dcd8567cee58e4c41c0/workspace.sqlite3`。备份清单 `.runtime/phase1b-production-snapshot.json`；备份前确认无活跃任务。
- 更新前有1份资料、0项任务、0份草案；更新后对documents/jobs/strategies原有列与行数进行SHA256核对，全部一致。测试样例没有进入正式data。
- 已重新核实旧PID39972的命令属于本项目8765启动器。旧聊天session在本线程不可访问；PowerShell Stop-Process报错，未删锁文件，改用同一已核实PID的Windows taskkill后标准启动脚本成功。
- 当前服务：`http://127.0.0.1:8765`；本线程终端session `96972`，PID `44320`（仅当次运行记录）。HTTP200；新转写路由存在；ASR/AI仍未配置。
- 正式页面Chrome复核：分享输入确为textarea，本地接口文档列出手动转写接口，0个page error。截图 `output/playwright/phase1b-production-import.png`、`phase1b-production-api.png`。使用独立浏览器，没有覆盖用户已有标签内容。用户应先保存旧页面未保存内容，再刷新。
- 临时8766、8768、8769、8881服务均已退出；最终仅8765项目服务监听。

### 真实能力与剩余条件

- B站公开样例第2P：真实下载并缓存2.07 MB / 97.94秒M4A**音频**，Chrome播放通过；无ASR保持待转写。
- 用户实际抖音分享短链：完整文案正确解析，302跳转到有效视频页面；下载器未取得aweme_detail并提示fresh cookies，**仍未取得媒体**，不能据此证明平台Cookie过期或必须登录。详见 `phase-1b-network.md`；不能将此项标为下载成功。
- 成功ASR/LLM流程只用明确替身验证接口，需要本地faster-whisper模型及用户选定的AI服务后才能做真实转写/策略提取。本期未下载模型、使用账户或新增会话授权。
- 参考项目未复制执行，选型依据保留在 `research/python-spider-evaluation.md`。后续会话设计为单独未实施建议，非本阶段隐藏完成项。
