# 实现验证记录

## 最新：Phase 2 本地 MVP（2026-11-10）

最终阶段状态见 [Phase 2 索引](docs/phase-2-index.md)。策略组合、独立回测与模拟盘、手机Dock及桌面导航已通过基本验收；补充发现的启动/恢复/批量信号时间问题已修复。

- 全量145项pytest通过（22.10s），含30项交易测试；日志 `.runtime/phase2-fix-evidence/full-pytest.log`。
- 二期交易与一期资料/媒体Chrome回归均通过，0浏览器错误；320/390/1440宽度验证。独立验收另有9组业务检查，详见阶段review报告。
- 协调复跑7个关键启动/恢复时钟场景通过；正式入口 http://127.0.0.1:8765 返回200，交易与原资料必需接口无缺失。
- 测试数据隔离；交易计算/SQLite/界面真实执行。资料AI/ASR/平台下载测试替身不代表外部连接成功；真实Tushare、券商、AI/ASR及云常驻尚未联调。

以下 Phase 1 及 Phase 1B 内容保留为历史记录。

# Phase 1 实现验证记录

最新阶段状态见 [Phase 1B 索引](docs/phase-1b-index.md)：78项最终测试及R1播放修复复核通过，8765已更新。下方Phase 1条目保留为历史记录。

日期：2026-11-09（Asia/Shanghai）。目录：`C:\Users\Admin\Desktop\quant`。本记录由实现聊天维护，独立基本验收由协调聊天管理。

## Phase 1B 协调最终实测

- 最终独立命令：`.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1b-coordinator-final -p no:cacheprovider --tb=short`，**78 passed in 17.13s**。原始旧库逐列保留脚本再次通过。
- 实际B站第2P链接经完整分享文案入口成功缓存M4A音频2,170,299字节、97.941111秒，并在Chrome播放。没有ASR时状态待转写，手动转写HTTP409说明配置要求。
- 用户实际抖音短链 `aU0BxZKBvVI` 完整文案解析正确，可跳到视频页面；yt-dlp未取得aweme_detail并提示fresh cookies，未获得媒体元数据或文件。该提示不能证明平台已确认Cookie过期或必须账号登录。没有读取用户cookies。
- 正式库一致性备份后安全重启8765；原1份资料及旧字段SHA256一致，任务/草案行数保持。新服务HTTP200，分享输入与新转写接口的本地文档Chrome检查通过，0个页面错误。生产截图 `output/playwright/phase1b-production-import.png`、`phase1b-production-api.png`。
- 真实平台证据及用户链接诊断见 [网络验证记录](docs/phase-1b-network.md)。真实ASR/LLM仍未配置、未验证；成功模型链路测试均为明确替身。

## 已运行的检查

| 检查 | 命令 / 方式 | 实际结果 |
|---|---|---|
| 后端测试 | `.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/test-run-final -p no:cacheprovider --tb=short` | **30 passed in 1.63s** |
| Python编译 | `.venv/Scripts/python.exe -m compileall -q app scripts tests` | 退出0 |
| JS语法 | `node --check frontend/app.js`、`node --check frontend/api.js` | 退出0 |
| 浏览器主流程 | `node scripts/ui_smoke.cjs`；`PLAYWRIGHT_CHANNEL=chrome`；`NODE_PATH`指向本机Codex bundled node_modules | PASS，0 page errors |
| ASR运行库 | 实际 import `faster_whisper`、`av`、`ctranslate2`、`yt_dlp` | 通过，版本1.2.1 / 19.0.2 / 4.8.5；yt-dlp 2026.10.26 |
| 环境读取 | `.venv/Scripts/python.exe scripts/check_environment.py` | Python3.12.14；AI与ASR均显示未配置，不返回密钥 |
| Windows入口 | `powershell -ExecutionPolicy Bypass -File scripts/start.ps1` | Uvicorn成功监听127.0.0.1:8765 |
| 单实例保护 | 已启动时运行 `.venv/Scripts/python.exe scripts/run.py --port 8768` | 退出1，明确提示同一data目录已有服务 |
| 本地API文档 | HTTP GET `/api/docs`及浏览器打开测试服务器的该页面 | 页面加载本地脚本，端点可见，无CDN依赖 |

浏览器脚本覆盖：文本/SRT导入 → 修改段落 → 保存 → 模拟提供方提取 → 原文定位 → 下载JSON → 修改原文使草案过期且禁用导出 → 刷新后保留数据；1440×1000桌面和390×844手机视口无横向溢出。测试服务端口8766，数据在单独的`.runtime/ui-*`，测试结束自动关闭。

## 测试内容

- 引用段落真实存在，原文片段逐字一致；时间戳由原文推导。
- 拒绝虚构引用、错误段落ID、编造阈值、额外字段、模型自报时间、重复JSON字段和非JSON输出。
- 缺少标的/周期/买卖/仓位/止损时明确提示；模糊规则待澄清，永不变成可执行订单。
- 不可信转写只进入独立用户消息；系统消息不拼入转写内容。
- OpenAI兼容与Ollama适配器的实际HTTP客户端构造：URL、JSON payload、鉴权范围、返回解析与引用校验；使用`httpx.MockTransport`，未连接模型服务。
- 接口401响应不泄漏服务端响应正文或测试密钥。
- SQLite保存/导出/服务重建后恢复，修订冲突，旧草案过期限制。
- 缺配置任务失败并可重试、重启在途任务标为中断、字幕上传、缺ASR的媒体失败状态。
- 不支持文件、超限文件、空白标题、跨站操作与非法Host被拒绝。
- URL域名/路径/协议校验、私有DNS地址与连接目的地址被拒绝。

测试驱动记录：最初测试因模块未实现失败；实现后校验测试9项通过。扩展测试暴露测试自身未恢复socket补丁，修正隔离后25项通过。空白标题回归测试先失败（201），添加非空白校验后30项通过。系统默认pytest临时目录在当前沙盒不可写，最终使用项目内新临时目录运行。

## 真实和模拟的区别

**真实已验证**：依赖安装与本机导入，HTTP服务启动、界面渲染和交互、输入解析、保存/导出、浏览器下载、SQLite持久化、版本控制、失败提示、ASR/模型未配置路径。

**模拟验证**：浏览器成功提取使用`tests/test_app.py`中的`FakeExtractor`；它仍通过生产引用校验器。导出和界面标记`TEST-ONLY / 模拟提供方`。协议适配使用MockTransport。以上不能作为真实模型质量或连接可用性的证据。

**未验证**：没有配置本地ASR权重，没有配置大语言模型或API凭据，未对真实教学视频执行ASR，也未执行真实模型提取、真实平台视频下载或Linux部署。没有下载模型、接触用户账户凭据、付费调用、真实交易。

真实链路的后续环境要求：准备faster-whisper模型目录并设置`ASR_MODEL_PATH`；选择已有OpenAI兼容服务或Ollama模型；使用有权访问的短媒体和平台链接做实测。平台登录/验证码/反爬造成的失败需要上传回退。

## 可查看的产物

- `output/playwright/desktop-empty.png`：桌面导入界面。
- `output/playwright/desktop-strategy-mock.png`：模拟提供方策略和原文证据，非真实AI结果。
- `output/playwright/mobile-import.png`、`mobile-workspace.png`：手机视口。
- `output/playwright/mock-strategy.json`：模拟提供方导出，仅供测试参考。
- `requirements-lock.txt`：实际安装版本快照。

接口文档修复说明：实现聊天在收到协调者R1消息时，已经将`/api/docs`改为本地OpenAPI查看页并完成Chrome验证；此后不再修改该片段，交由协调者的独立修复/验收流程核实。最终全项目验收以协调聊天索引为准。

## 标准启动与锁的复核

协调者报告再次启动提示数据目录占用后，确认原先本实现聊天启动的PID34100仍在运行，HTTP访问8765返回200，读取锁文件也被操作系统明确报告已有进程锁定。`Get-NetTCPConnection`在沙盒内返回“拒绝访问”，若隐藏错误会得到空结果，因此不能据此判断端口没有监听。不是锁机制误报，未改写互斥逻辑。

仅停止本聊天创建的PID34100后，直接运行 `& './scripts/start.ps1'` 成功启动新进程PID39972；随后`/api/status`与`/api/docs`均返回200。根据协调者最新指示，服务保留在127.0.0.1:8765运行供交付（终端session29963）。未终止无关进程。锁文件长度增加是以append模式写入标记造成，不影响锁定范围或互斥；判断服务状态应使用HTTP探测及进程归属。


## Phase 1B 增量验证（2026-11-09）

本节覆盖本次链接导入改动，前面的 Phase 1 记录保留为历史证据。Phase 1B 改为无 ASR 时先缓存媒体；不再适用前文“缺ASR的媒体任务失败”的旧行为。

- 最终后端命令：`.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1b-final-probe -p no:cacheprovider --tb=short`，结果 **69 passed in 5.86s**。
- Python编译：`python -m compileall -q app tests`；JS：`node --check frontend/app.js`、`frontend/api.js`、`scripts/ui_smoke.cjs`，均退出0。
- 最终浏览器：`node scripts/ui_smoke.cjs`，bundled Playwright + Chrome，**PASS，0 page errors**。最终数据目录 `.runtime/ui-1794210804808`，脚本启动并关闭8766测试服务。端口已占用时脚本拒绝附着，生产8765未操作。
- 覆盖分享文案/多URL/恶意或错误链接/B站分P；不依赖ASR下载保存；手动缓存转写、失败后只读缓存重试、重复活跃任务拒绝、丢失缓存不重下载；元数据、真实WAV类型/时长/大小检查、下载前拒绝超限/直播/合集/错误页面；固定错误信息不含原始令牌；旧数据库迁移与草案回归。
- Python实际connect/connect_ex及DNS解析目的IP固定测试通过；PyAV探测采用file协议白名单，生成的本地网络引用清单测试未产生HTTP请求。
- 观察截图时发现极快下载完成后侧栏仍显示默认标题；新增浏览器断言先复现失败，修复当前资料标题同步后通过。
- 浏览器分别查看1440×1000与390×844视口，缓存音轨为audio控件，明确显示“已缓存音频（仅音轨）”“已获取，待转写”，无模型时禁用开始转写并显示配置说明。截图：`output/playwright/phase1b-cached-audio-test.png`、`phase1b-mobile-cached-test.png`。
- 所有成功平台/ASR/策略调用均为**测试专用边界替身**；缓存是生成的1秒WAV，不是实际平台素材。外部服务未被这些测试调用；测试替身只在tests中启用，没有生产配置开关。真实平台小样本由协调线程另行验收；本节不宣称真实下载或模型可用。

实现范围、状态和边界见 [docs/phase-1b-implementation.md](docs/phase-1b-implementation.md)。未修改依赖、下载模型、使用用户凭据或清理用户data。基本复查完成；阶段最终接受与8765重启由协调线程负责。

## Phase 1B R1 跟进修复验证（2026-11-09）

本节由可见修复线程补充，原验收结论保留在 `docs/phase-1b-review.md`。修复本地上传/旧缓存缺少媒体类型导致播放器和媒体证据定位消失的回归；详细方案、红绿测试和局限见 [docs/phase-1b-fix.md](docs/phase-1b-fix.md)。

- 新增9项回归测试修复前全部失败于缺少元数据；修复后全项目 **78 passed in 21.30s**。命令：`.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1b-fix-full -p no:cacheprovider --tb=short`；日志 `.runtime/phase1b-fix-pytest.log`。
- 真实PyAV子进程读取有效WAV（包括改成`.mp4`后缀仍认作音频）和静音H.264视频；旧库补字段、首次打开恢复类型，逐行确认原资料列、转写/版本、所有草案和历史任务不变。失败/超时/超限仍保留缓存；含HTTP引用的伪WAV不产生网络请求。原有download/connect/connect_ex安全及缓存转写测试保持通过。
- 扩展 `node scripts/ui_smoke.cjs`，Chrome **PASS，0 page errors**。独立8766服务及 `.runtime/ui-1794211960314`；本地WAV、H.264、历史WAV实际播放时间均超过0.2秒，历史证据定位1秒；无效媒体保留下载入口。旧分享导入、缓存转写失败/重试、校对、模拟提取/导出和手机布局继续通过。
- 浏览器首次执行在历史资料点击后立即断言，遇到异步渲染时序问题；脚本改为等待对应资料标题再检查，后续完整执行通过。没有为此改变产品逻辑。
- `frontend/app.js` 和 `scripts/ui_smoke.cjs` 的Node语法检查退出0。截图及结构化结果：`output/playwright/phase1b-fix-*`。本次真实的是本地媒体探测、持久化及浏览器播放；平台下载/ASR/LLM仍为显式测试替身。未操作正式data或8765，未使用8768/8769，未重跑真实平台下载或配置模型。
