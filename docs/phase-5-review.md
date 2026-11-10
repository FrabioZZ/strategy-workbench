# Phase 5 — 独立基本验收

日期：2026-11-10，Asia/Shanghai。可见验收聊天：`01a1c5d0-38ee-7f53-a73b-09086adbe103`。工作目录 `C:/Users/Admin/Desktop/quant`，非 Git，branch/worktree 不适用。

## 结论：Phase 5 基本验收通过

两项跟进修复均已交付，已检查最终实现并独立复验。**Phase 5 范围内没有剩余必须修复项**。接受的是下述受检源码快照与本阶段功能；不代表 Phase 6 最终系统包已验收或已部署。

按用户要求只复核需求、主流程和明显回归，不做对抗审计。未修改产品代码、正式数据库、`.env` 或凭据，未重启 8765；未创建线程或后台代理。独立测试与证据均在 `.runtime/phase5-review/`。

协调新增交接：Phase 6 可见协调聊天 `01a1c5d2-ffb5-7e31-958b-e559c07f63e1` 正修改共享 `app/trading/`、`frontend/trading.js`、`index.html` 局部及 `config.py`。本报告只作 Phase 5 功能及两项修复验收，不以全仓哈希持续不动为前提；最终全系统回归、部署、数据保全与打包归 Phase 6。此验收不覆盖 Phase 6 新指标和日期范围功能。

## 已完成的独立检查

- 已阅读设计、索引、集成、后端、前端与转写工作记录，以及设置/HTTP 客户端/路由/提取/交易映射/转写队列/原文与校正快照/前端实现。
- 首轮全量 Python：`301 passed, 1 failed, 104 warnings in 35.09s`。日志 `.runtime/phase5-review/pytest-initial.log`。本次是在后端仍补测试时运行的中间快照，不能据此宣称最终源码通过。
- 首轮失败是 `tests/test_ai_backend.py::test_mapping_cannot_drop_unextracted_financial_filter`：在标准阈值策略的原始转写中加入 `ROE需要高于15%`，`validate_proposal` 仍返回可执行规则。后端已增加完整转写子句核对；独立复跑后端测试 **38 passed in 2.29s**，包含该失败用例，日志 `.runtime/phase5-review/pytest-backend.log`。此中间交付问题已关闭，最终仍纳入全套回归。
- 转写浏览器探针的隔离副本：1/1 通过，覆盖自动阶段、无假百分比/播放器、常亮提示降级、短时网络错误恢复、缓存重试、完成标记、全文默认折叠、刷新、证据与校对、手机无溢出及缺 ASR 不误报。日志 `.runtime/phase5-review/transcription-ui.log`。
- AI 浏览器探针的隔离副本：通过；`mountedFallback=false`、`statusReads=4`、`testCalls=2`，0 页面错误。覆盖配置/连接失败/Key 清空/改地址、校正摘要、参数回填、确认默认关闭、无效或过期建议拒绝、其他编辑焦点和手机布局。日志 `.runtime/phase5-review/ai-ui.log`，报告 `.runtime/phase5-review/ai-ui/phase5-ai-result.json`。API 为明确替身。
- 完整应用集成探针隔离副本通过：`.runtime/phase5-review/integrated-1794320248561/report.json`，`passed=true`、`errors=[]`。网页保存配置 → 真实 Windows DPAPI → SQLite → 提取命名 → AI 参数 → 保持未确认 → 人工确认保存 → 回测/本地回放/Backtrader。前两者各 3 笔成交完全一致，Backtrader 3 笔成交且信号一致；均使用同一保存组合。仅模型 HTTP 响应与行情为夹具。日志 `.runtime/phase5-review/integrated-ui.log`。
- 已实际查看本次生成的转写桌面、AI 设置 320px、AI 参数 390px、校正详情、完整应用回测 390px 截图；布局可用，文字可读，无横向溢出。截图在 `.runtime/phase5-review/{transcription-ui,ai-ui,integrated-ui}/`。
- 浏览器集成主流程在 6 秒内成功；受限环境阻止探针清理自己创建的 Python 子进程，因此在宿主权限下按已核实的命令行/隔离数据目录关闭这两个测试进程。脚本最终退出码 0，未触碰正式服务。这是测试清理的环境限制，不是产品缺陷。
- 语言修复交付后，已读 `phase-5-language-fix.md`、最终 `review.py/language.py` 及 49 项专项用例。两段用户实际 ASR 文本在明确模型建议替身下独立复测均采用，报告 `.runtime/phase5-review/language-probe.json`；未硬编码真实样例，局部纠错与敏感含义检查分离。
- 独立审计持久化探针通过：同一资料含可采用的“情续→情绪”和需拒绝的“10元→12元”建议，原文保留、采用/拒绝各 1 条审计、导出及重启保持、自动命名保留，待确认问题使映射 `ready=false/rules=null`。报告 `.runtime/phase5-review/review-audit.json`。
- 语言修复后的全量运行：**378 passed, 104 warnings in 38.93s**，日志 `.runtime/phase5-review/pytest-final.log`；警告均为 Backtrader 既有 `datetime.utcnow` 弃用提示。该运行与旁白修复/Phase 6 并行，因此最终仍补针对 Phase 5 的固定范围检查，不把它冒称最终全系统发布验证。
- Node 现有链接桥接单元测试 2/2 通过；6 个前端 JS 语法检查均退出 0。日志 `.runtime/phase5-review/node-unit.log`、`.runtime/phase5-review/frontend-syntax.json`。

## 最终修复与主流程确认

- 已读 [语言修复](phase-5-language-fix.md) 和 [旁白映射修复](phase-5-mapping-fix.md)，检查最终 `review.py/language.py/mapping.py/mapping_language.py` 与相应测试。普通旁白按完整子句正向识别，不贡献参数证据；ROE、额外数值条件、时序/周期和未知限制继续返回问题。两项修复均关闭。
- 两项修复完成后的相关 Python 回归：**220 passed, 104 warnings in 19.47s**，退出 0。覆盖 AI 后端/语言/旁白映射、自动转写、链接和媒体、ASR 运行时、旧应用/adapter/引用校验、组合/回测/本地模拟/Backtrader。日志：[pytest-phase5-final.log](../.runtime/phase5-review/pytest-phase5-final.log)。
- 最终浏览器全链路额外加入 `大家好，今天和大家分享这个方法，感谢观看。`，并断言首次配置预填地址/模型但仍未配置且不能测试连接。**通过**，报告：[integrated-1794320626836/report.json](../.runtime/phase5-review/integrated-1794320626836/report.json)。同一人工确认组合，回测和本地回放成交完全一致（各3笔），Backtrader也是3笔且信号一致；0页面错误，1440/390无横向溢出。
- 最终复跑期间 Phase 6 将回测指标拆成两组，旧探针 `.metrics` 唯一元素断言因匹配2个元素失败（报告 `integrated-1794320603929/report.json`），此前引擎断言已通过。仅调整验收副本为取首组指标后全流程通过；没有为测试修改产品。该失败属于并行页面变更后的探针定位失配。

最终相关测试命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_ai_backend.py tests/test_ai_language.py tests/test_ai_mapping_narration.py tests/test_auto_transcription.py tests/test_link_import.py tests/test_local_media.py tests/test_asr_runtime.py tests/test_app.py tests/test_adapters.py tests/test_validation.py tests/test_trading.py tests/test_phase3_integration.py tests/test_paper_engine.py tests/test_paper_service.py -q --basetemp .runtime/phase5-review/pytest-phase5-final -p no:cacheprovider
node .runtime/phase5-review/integrated-ui.cjs
```

| 用户要求 | 结果与证据 |
|---|---|
| 链接自动转写、真实进度状态、常亮提示、无播放器、默认不展示全文 | 独立浏览器主流程及46项对应Python覆盖；协调真实B站/本地ASR证据已复核。Wake Lock拒绝时仍有清晰提示，不承诺操作系统永远常亮 |
| 本机多模型设置、DPAPI、密钥不回显、供应商直接认证说明 | 真实Windows DPAPI生命周期测试和真实应用浏览器保存通过；页面明确凭据/内容发给所选供应商、不经产品云端；目的地变化不能复用旧Key |
| AI主动校正、自动命名、原文和审计、区分引文版本 | 49项语言用例、两段实际ASR文字探针、独立审计保存/重启/导出检查通过；数值歧义保留原文并阻止映射；校正稿引用有版本标签 |
| AI建议经用户确认接入现有ma/threshold与三引擎 | ma/threshold语义与引用测试通过；建议confirmed=false，未确认不能就绪；含普通旁白的真实应用全链路通过三引擎 |
| 打板另阶段，不在Phase5强行映射 | 本阶段映射对现有DSL不能完整表达的条件拒绝就绪；新增指标、日期范围和打板能力属于Phase6验收范围 |

## 受检源码与跨阶段边界

最终相关验证前快照：**2026-11-10 22:23:18 +08:00**；后快照：**22:24:08 +08:00**。Phase 5 的25个直接相关源文件/测试在两次快照间内容一致，详见 [phase5-source-sha256.json](../.runtime/phase5-review/phase5-source-sha256.json)。包含核心AI、原文/任务管线、配置、组合接入、前端与新增测试；具体文件和完整SHA256在清单内。

整个 `app/frontend/tests` 源文件后快照共88个：[完整SHA256文本清单](../.runtime/phase5-review/source-sha256-final.txt)、[JSON元数据清单](../.runtime/phase5-review/source-sha256-final.json)。只读取产品源文件，没有读取或哈希用户Key配置、`.env`、正式数据或数据库。

并行Phase6在验证期间新增/修改了 `app/ai/capabilities.py`、`app/trading/engine.py`、`paper_service.py`、`router.py`、`service.py`，见 [source-stability.json](../.runtime/phase5-review/source-stability.json)。因此**全仓前后快照不相同**，没有宣称全系统在固定最终源码上通过。Phase6应对后续合并后的实际发布源码重跑最终系统回归、生成发布哈希并部署；本报告的受检清单不是发布包清单。

## 验证边界

已读取协调提供的真实 Bilibili → 本地 ASR 报告 `.runtime/phase5-live-1794319807735/report.json`：真实 29.67 秒音轨自动转写 9 段、两任务成功、0 媒体播放请求、刷新保留、桌面/手机通过；这是复核协调证据，不冒称本验收聊天重新下载了真实平台视频。

无用户真实 API Key；HTTP 替身验证协议与应用控制流程，不证明真实供应商连通、真实模型纠错质量或策略有效性。打板执行不属于本阶段。
