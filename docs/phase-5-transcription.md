# Phase 5 — 转写体验实施记录

范围：`frontend/app.js`、`index.html`、`style.css`；`app/jobs.py` 仅下载与自动转写衔接；相关转写测试。工作目录 C:/Users/Admin/Desktop/quant，非 Git，branch / worktree 不适用。按既有 Phase 5 设计直接执行，不创建额外线程或代理。

## 方案与接口

- 下载完成和新转写任务排队必须在同一 SQLite 事务内提交，以免前端观察到无活动任务且尚未转写的间隙。沿用独立 download / transcribe 任务与原重试 API。
- 缺 ASR 时缓存下载成功，但资料仍为 awaiting_transcription；不显示转写成功勾选。已有转写内容不自动覆盖。
- 默认不显示播放器或全文；校对面板按需展开，证据按钮打开面板并定位段落。
- 处理中使用不确定进度条和保持程序打开、设备唤醒的提示；Wake Lock 只作可选浏览器增强，不保证设备常亮。
- `renderDocument()` 末尾派发 `document-rendered`，detail 为完整 document。index 添加 `ai-settings-root`、ai.css、defer ai.js（app/trading 之后）。AI 校正摘要由独立 ai.js 负责。
- 已授权共享目录精确编辑；不改正式数据、.env、凭据，不重启 8765 服务。独立基本验收由协调安排。

## 实施与验证

- 已实现：download 成功与 transcribe queued 原子提交；同一串行 worker 继续执行转写。下载历史与 ASR 历史独立保留，失败的 ASR 继续走原缓存重试接口。ASR 未配置则保持等待状态，不排入必然失败的识别任务。
- 已实现：无播放器、默认折叠原文、完成勾选、无百分比进度、设备唤醒提示；保存最近打开的资料，刷新自动恢复；轮询短暂失败继续重连且不误报完成；Wake Lock 被拒绝时降级为提示。
- 已实现：AI 静态文件与设置挂载点、document-rendered 事件、供应商中性提示；证据的 `transcript_version=corrected` 明确显示“校正版依据 · 对照原始段落”，按钮展开原始文本供对照，校正摘要及详情仍由 ai.js 显示。
- 后端测试 RED：新增 3 项中，自动接续与自动失败缓存重试先出现预期失败（2 failed / 1 passed）。修复后与旧链接测试合并 30 passed。
- 相关回归：`.venv/Scripts/python.exe -m pytest tests/test_auto_transcription.py tests/test_link_import.py tests/test_local_media.py tests/test_asr_runtime.py -q --basetemp .test-tmp/phase5-transcription-media -p no:cacheprovider` → **40 passed**。覆盖 ASR 不可用、缓存重试、重启恢复、原文不覆盖、真实媒体探测和 ASR 解码兼容；自动下载/识别流程使用明确的 worker 替身。
- 最终相关 Python 回归：`.venv/Scripts/python.exe -m pytest tests/test_auto_transcription.py tests/test_link_import.py tests/test_local_media.py tests/test_asr_runtime.py tests/test_app.py -q --basetemp .test-tmp/phase5-transcription-final -p no:cacheprovider` → **46 passed in 10.77s**。
- 浏览器使用现有 playwright-core 与 headless Chrome，临时 loopback 静态服务和内存 API 替身；不占用或重启正式 8765。`node --test tests/test_transcription_ui.cjs` → **1 passed**（完整主流程，约 10 秒），`node --check frontend/app.js` → **exit 0**。浏览器探针覆盖导入提示、下载→ASR、不确定进度、唤醒提示、Wake Lock 拒绝降级、网络错误后继续轮询、失败缓存重试、完成勾选、默认无播放器/全文、刷新恢复、document-rendered 契约、供应商名称、校正版标签、证据展开、校对保存、390px 无横向溢出及缺 ASR 不误报成功。
- 已目视检查桌面/手机截图：[桌面](../output/playwright/phase5-transcription-desktop.png)、[手机](../output/playwright/phase5-transcription-mobile.png)。浏览器探针只执行本工作组 app.js，AI 与交易模块由各自工作组及协调验收；静态入口已挂载实际 AI 文件。
- 2026-11-10：本工作组实现与自检完成，交给协调进行整阶段集成和可见基本验收。检查范围为需求与主流程，没有运行对抗审计。
- 本记录采用 executing-plans / test-driven-development / verification-before-completion 的逐项验证原则；现有授权要求留在共享非 Git 目录，不建立 Git worktree，不派生 review 子代理。

## 协调集成注意事项

- 无接口破坏性变更。下载成功后同时存在转写 job，调用方若判断整份资料完成，应读取 `active jobs` / `segments`，而非只轮询 download job 的 succeeded。
- AI 前端可用现有 `[data-evidence]`；新增 `data-transcript-version` 提供明确版本。原始段落 id 和校对表单接口不变。
- 整阶段真实平台下载→真实 ASR 和正式服务备份部署由协调执行；本工作组没有修改正式资料、模型配置、.env 或凭据。
