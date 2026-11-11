# Phase 8 基本验收记录

## 状态与边界

2026-11-11，独立基本验收通过。真实云连接、计费与识别质量对照仍待验证。

- 验收聊天：`01a1c8a2-4fad-7c81-b9f0-d2094d3b60a9`；协调聊天：`01a1c89a-52cc-7d60-8029-ee09c2d93417`。
- 目录/分支：`C:/Users/Admin/Desktop/quant` / `main`，复用 checkout。
- 实施聊天：`01a1c89d-af69-7950-b4bd-fd82b4bd3d13`。验收对象为 [实施记录](phase-8-implementation.md) 标记可验收的 `quant/main` 工作区。隔离 portable 的清单与验收结束时的 63 个应用和前端文件哈希一致。
- 基本验收覆盖需求、主要流程及明显回归，不开展对抗审计。仅写本文件与隔离 `.runtime` 证据，产品修复交实施聊天。
- 不读取、展示正式用户 Key，不变更正式用户资料，不执行真实付费云识别。
- 既有 `app/ai/client.py`、`docs/phase-5-index.md`、`tests/test_ai_client.py` 不计为 Phase 8 成果。

## 官方接口核对

核对日期：2026-11-11。重要来源更正：指定的 [Fun-ASR 页面](https://help.aliyun.com/en/model-studio/fun-asr-recorded-speech-recognition-http-api) 当前内容为 Fun-ASR，未列新版 Qwen 模型和 `input.context`。新版模型应以 [Qwen-Audio-ASR-Filetrans HTTP 专属文档](https://help.aliyun.com/en/model-studio/qwen-audio-asr-filetrans-http-api) 为准；[模型概览](https://help.aliyun.com/en/model-studio/asr-model) 与[模型页](https://help.aliyun.com/en/model-studio/qwen-audio-3-1-asr-flash-filetrans) 可交叉核验。旧 [Qwen-ASR API](https://help.aliyun.com/en/model-studio/qwen-asr-api-reference) 的单值字段不能迁移到新版。

专属文档核对要点（用于后续合同 fixture，不代表服务实测）：

- 示例模型为 `qwen-audio-3.1-asr-flash-filetrans`；`input.file_urls` 为仅含一个 URL 的数组。`input.context` 使用消息数组，用户文本类型为 `input_text`；单轮上下文最多 400 字符，需核验主题截断。
- `parameters` 必须存在，词表为 `parameters.vocabulary` 的词语到整数权重映射。
- 提交使用 `POST /api/v1/services/audio/asr/transcription`，携带 Bearer、JSON 和 `X-DashScope-Async: enable`；按 `task_id` 在 `GET /api/v1/tasks/{task_id}` 查询。文档推荐北京/新加坡 Workspace 专属域名，并列出旧 DashScope 域名迁移关系。
- 顶层成功仍需核对子任务状态，再读取 `transcription_url` 的 JSON。结果位于 `transcripts[].sentences[]`，`begin_time` / `end_time` 为毫秒，应用须正确转换。
- 文档限制临时 OSS URL 的使用场景；[上传专属文档](https://help.aliyun.com/en/model-studio/get-temporary-file-url) 定义 `GET /api/v1/uploads?action=getPolicy&model=...` 取得 `data` 中的凭证，再 `POST data.upload_host`。multipart 包含 `OSSAccessKeyId`、`Signature`、`policy`、`key`（上传目录加文件名）、`x-oss-object-acl`、`x-oss-forbid-overwrite`，`file` 字段最后，不能把 DashScope Bearer 当上传表单凭证。临时 OSS 调用头需核验 `X-DashScope-OssResourceResolve`。该来源同时声明临时空间不适用于生产；若交付仅支持临时上传，接受记录需明确这一使用边界。

北京默认域名与新加坡 Workspace 专属任务域名由测试覆盖。浏览器集成测试在应用的 ASR worker 边界接入真实 Qwen 适配器及 HTTP mock，验证 WAV 和 multipart 上传、任务提交、续查及结果读取。临时上传和实际工作空间服务的可用性须用真实凭据验证。

## 正式验收检查表

| 编号 | 需求与通过标准 | 证据方式 | 状态 |
|---|---|---|---|
| A1 | 保留本地 small 与自动接续 | Python 回归和隔离 portable 实际加载 small。实施记录另有 24 秒真实本地上传和转写结果 | 通过 |
| A2 | 上传、提交、查询、结果下载与异常处理符合新版合同 | HTTP mock 检查方法、认证、multipart 字段及顺序、提交字段和响应解析 | 合同通过 |
| A3 | 金融词表与资料主题进入转写 | 浏览器集成验证 `市盈率: 4` 和自填主题。静态确认 400 字符截断及本地 `initial_prompt` / `hotwords` | 通过 |
| A4 | 文本 AI 和 ASR 凭据独立，DPAPI 保存并可重启恢复 | 两个虚构 Key 经真实 DPAPI 保存，公开接口与配置文件无明文。重启后续查继续使用 ASR Key。切回本地清除 ASR Key，文本 Key 仍保留 | 通过 |
| A5 | 设置披露上传和计费，由用户主动启用和启动 | 从浏览器设置操作，未勾选拒绝保存。启用后上传媒体只缓存，点击开始才产生模拟云请求 | 通过 |
| A6 | 历史资料通过有父来源的副本重转写并保留历史策略证据 | 浏览器对旧数据库字段执行迁移。副本重转写完成后，父资料导出逐项一致，保留原始转写时间戳、校正文和审计变化。正常资料也验证了父来源跳转 | 通过 |
| A7 | 缓存复用、失败或超时后从正常入口重试 | 完成结果本地复用及超时续查用例通过。浏览器模拟首轮查询网络中断，重启后从资料页重试，只增加查询及下载结果请求 | 通过 |
| A8 | 毫秒时间戳正确换算，保留原始段落和证据定位 | fixture 的 321–2421 ms 存为 0.321–2.421 秒。校对后原段落仍在导出，策略证据按钮定位校对稿 | 通过 |
| A9 | portable 自带新增模块和本地模型，缺云 Key 可启停 | 隔离 0.6.1 portable 刷新源文件，使用随包运行时启动并执行真实媒体探测、small 加载、Chromium 和停止器 | 通过 |
| A10 | 完整 Python/Node 回归与浏览器基本主流程 | 452 个 Python 和 3 个 Node 测试通过，真实后端浏览器流程通过 | 通过 |
| A11 | 同段真实 small/Qwen 质量对照 | 已有 480.885 秒授权金融视频的 fresh small 基线，耗时 143.61 秒、282 段，与历史保存结果一致 | 待 ASR 专用 Key 和人工评分，未做云对照 |

## 已读现有回归与证据约束

- `tests/test_auto_transcription.py` 使用真实队列/数据库/API 加 worker fixture，已有自动转写、缓存失败重试及重启、已校对内容不被下载重试覆盖的检查。
- `tests/test_transcription_ui.cjs` 使用内存 API fixture，覆盖状态/重试/刷新/校对/证据入口；不能据此声称真实后端到云端已通过。该测试默认写 `output/playwright`，正式验收需改用隔离副本/运行脚本将证据写入本聊天允许的 `.runtime` 路径，不改原测试文件。
- `tests/test_asr_runtime.py` 验证真实 PCM 的 PyAV/faster-whisper 解码兼容，不能替代 small 模型加载和识别质量验证。
- `scripts/verify_portable.py` 会启动分发目录、写 `user-data` 并执行停止器；只可对隔离验收包运行，不能对正式用户运行目录执行。
- 本机无可用于此阶段的独立 ASR Key，按协调交接记录。验收使用虚构凭据和本地响应模拟。

## 正式回归结果

证据位于 `.runtime/phase8-review/`，应用、资料和配置均在隔离路径运行。

- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .runtime/phase8-review/pytest-final -o faulthandler_timeout=45`，退出码 0。452 通过，126 条既有 Backtrader `utcnow` 弃用提示。[日志](../.runtime/phase8-review/pytest-final.log)
- `node --test .runtime/phase8-review/node-suite/tests/test_douyin_browser.cjs .runtime/phase8-review/node-suite/tests/test_transcription_ui.cjs`，退出码 0。3 通过。用例及其输入副本位于隔离目录。[日志](../.runtime/phase8-review/node-final.log)
- `node .runtime/phase8-review/browser.cjs`，退出码 0。Chrome 连接真实 FastAPI、SQLite、DPAPI 和媒体探测进程，云交互使用 HTTP mock，文本 AI 策略使用本地 fixture。第一次受限沙箱运行遇到 Windows 回环套接字权限错误，本机权限下通过。[证据](../.runtime/phase8-review/browser-HTmYOU/browser-result.json)
- `.venv/Scripts/python.exe -B scripts/verify_portable.py .runtime/phase8-review/portable`，退出码 0。依赖、HTTP API、内置行情、媒体探测、small 加载、Chromium 和停止器均通过。使用上一版随包运行时和当前源文件刷新隔离副本。发布 ZIP 未重建。[证据](../.runtime/phase8-review/portable-verification.json)
- 两个变更的前端脚本通过 `node --check`，`git diff --check` 通过。未发现需交实施修复的基本主流程问题。

云端实测待用户在应用中配置独立 ASR Key，再用同一授权样本作人工对照。已有 [small 基线](../.runtime/phase8-evaluation/fresh-small-baseline.json) 可复用。临时 OSS 的适用范围与按 Token 计费以官方说明为准。
