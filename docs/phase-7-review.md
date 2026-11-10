# Phase 7 — 用户流程与界面基本验收

日期：2026-11-10，Asia/Shanghai。验收聊天：`01a1c5f6-cde7-7ae1-8336-a637c90f720d`；协调聊天：`01a1c5ee-a547-7f53-b4ca-e8aee5c4a90d`；实现聊天：`01a1c5f4-fcd9-7331-a0b8-5a5627a42106`。

工作目录 `C:/Users/Admin/Desktop/quant`，分支 `main`，复用共享工作区，无新增 worktree。

## 结论：源码基本验收通过

实现聊天已完成；独立验证 **432 项 Python、2 项 Node 单元测试、转写浏览器测试及四组浏览器主流程通过**。本轮范围内无剩余必修问题。验收覆盖需求、主流程和明显回归，不代表便携包或 GitHub 发布已完成。

已阅读 `phase-7-index.md`、`PRODUCT.md` 当前范围、`phase-7-ui.md`、最终前端差异及既有测试。通过 `wait_threads` compact snapshot 和 `afterCursor` 等待，观察到实现 turn `01a1c5f5-01d6-7bb1-a7d2-2d6c037e8e18` 在 **23:07:17 +08:00** 完成后才启动独立回归；没有把实现编辑中的中间状态当作最终通过。

本轮仅做需求、主流程和明显回归的基本验收，不做对抗审计。只更新本报告及隔离测试证据，不修改产品代码、脚本、正式数据库或凭据，不 commit/push，不创建其他聊天或后台代理，不发送跨聊天消息。截图与验收证据输出到 `output/playwright/phase7-review/`；测试数据库只使用隔离目录。

## 需求与源码检查

| 要求 | 独立验收结果与定位 |
| --- | --- |
| 删除特定样例验证叙事 | 通过。`frontend/trading.js:63` 的指标库已删除整块一进二验证说明，前端 HTML/JS/CSS 搜索无“一进二”“打板”“日线验证边界”命中。保留普通“首个涨停收盘信号”预设及其真实执行时点，没有把它当作产品定位或已验证策略。 |
| 真正清理注释，保留状态 | 通过。已检查 DOM 模板删除与缩短，而非全局隐藏 `.helper`。`frontend/app.js:37`、`:39`、`:103` 仍显示 ASR/AI 配置、发送目的地、进度、失败及重试；组合未就绪、保存状态、数据读取失败、模拟状态均保留。数据与计算规则改为原生 details（`frontend/trading.js:324`）。 |
| 盈亏优先 | 通过。`frontend/trading.js:304` 与 `frontend/paper-external.js:66` 先显示阶段盈亏和收益率，再显示资产、回撤及费用。研究计价、演示行情及本地模拟标签仍存在。结果聚焦与清空历史选择检查通过（`frontend/trading.js:282`、`:303`）。 |
| 资料到已确认策略 | 通过。真实本地应用的配置保存、Windows 加密存储、文本导入、校正/命名/草案提取、参数回填、默认未确认、人工确认、保存与刷新重载均覆盖。模型 HTTP 响应为明确替身。转写专项覆盖失败重试、短时断网恢复、完成勾选、全文默认折叠、证据跳转及校对保存。 |
| 日期与真实引擎执行 | 通过。日期默认值、标的切换、倒序阻止、刷新保留、起日前预热、区间内净值、保存记录及重载金额均覆盖。未复权回测、模拟单步、独立 Backtrader 运行正常。 |
| 最新报价与估值 | 通过。`frontend/quotes.js:57` 的持仓/现金账户估值、约45秒自动刷新、手动缓存、源故障、服务503、恢复、隐藏页面暂停轮询均覆盖。报价前后历史账本完全一致。 |
| 手机与桌面 | 通过。四工作区在 320/390/768/1024/1440px 检查页面宽度、表单及按钮实际左右边界、可用按钮高度、导航状态。`product.css:12` 的横向裁剪未用于掩盖控件越界。键盘切换工作区、导入页签、Enter 展开、刷新保持详情展开均通过；`:21` 定义可见焦点。宽表保留局部横向滚动。 |
| 指定设计技能 | 已复核实现文档及四份来源/版本/哈希记录，采用范围与现有产品一致。HallMark 专用 render tier 未运行的限制已如实记录；本验收使用项目 Playwright 实际截图与交互。没有声称完成四技能所有检查。 |

## 独立执行证据

以下命令均在最终实现完成后实际执行，退出码均为 **0**。浏览器复用现有探针，以 PowerShell here-string 管道交给 `node`，通过 `Module._compile` 在内存中调整输出路径和隔离服务器启动/退出；没有改写产品或仓库脚本。探针源哈希见 [probe-sources.json](../output/playwright/phase7-review/probe-sources.json)。

| 实际执行入口 | 结果 | 证据 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests -q -p no:cacheprovider --basetemp .runtime/phase7-review/pytest-full --tb=short` | **432 passed，126 warnings，48.22s**。警告为既有 Backtrader `datetime.utcnow()` 弃用提示。 | [pytest-full.log](../output/playwright/phase7-review/pytest-full.log) |
| `node --test tests/test_douyin_browser.cjs` | **2 passed / 0 failed** | [node-unit.log](../output/playwright/phase7-review/node-unit.log) |
| `node --check`（frontend 下全部6份 JS）；`git diff --check -- frontend scripts/phase6_ui_smoke.cjs scripts/phase7_ui_smoke.cjs` | 语法与空白检查通过 | 本聊天命令输出，退出0 |
| `node` 内存执行 `scripts/phase6_ui_smoke.cjs`，`UI_SMOKE_PHASE=phase7` | **passed=true，errors=[]，32指标，externalEngineVerified=true**；真实 API、SQLite、回测与模拟引擎。 | [main-ui.log](../output/playwright/phase7-review/main-ui.log)、[phase7-ui-result.json](../output/playwright/phase7-review/phase7-ui-result.json) |
| `node` 内存执行 `tests/test_transcription_ui.cjs` | **1 passed / 0 failed**；API/ASR 为明确夹具，测试真实转写前端状态。 | [transcription-ui.log](../output/playwright/phase7-review/transcription-ui.log) |
| `node` 内存执行 `scripts/phase5_ai_ui_smoke.cjs` | **passed=true，mountedFallback=false，errors=[]**。配置保存/删除、连接失败、参数确认、过期或无效回填、手机布局通过。 | [ai-ui.log](../output/playwright/phase7-review/ai-ui.log)、[phase5-ai-result.json](../output/playwright/phase7-review/phase5-ai-result.json) |
| `node` 内存执行 `.runtime/phase5-review/integrated-ui.cjs` | **passed=true，errors=[]**。实际配置/DPAPI/导入/提取/组合API和三引擎；只有模型HTTP及行情为夹具。回测与本地回放各3笔成交完全一致；Backtrader也是3笔、信号一致。刷新后已保存回测、模拟及独立回放可展示。 | [integrated-ui.log](../output/playwright/phase7-review/integrated-ui.log)、[integrated-result.json](../output/playwright/phase7-review/integrated-result.json) |
| `node` 内存执行 `scripts/phase4_ui_smoke.cjs` | **passed=true，errors=[]**；自动刷新 **44988ms**，明确注入503产生 **1条预期控制台503**，无其他错误。真实API、人工报价/持仓，估值刷新不改账本。 | [quotes-ui.log](../output/playwright/phase7-review/quotes-ui.log)、[phase4-result.json](../output/playwright/phase7-review/phase4-result.json) |

主流程研究回测的实际区间为 **2024-02-13～2024-04-02**，起日前预热 **30** 根；初始资产 **10,000.00**，结束资产 **10,743.74**，阶段盈亏 **+743.74**，收益率 **+7.44%**。金额与API存储值一致。这是人工行情上的真实引擎计算，不是实际市场或视频策略收益。独立 Backtrader 主流程消费80根人工日线，展示盈亏 **+5,182.78**、收益率 **5.18%**，也与引擎净值核对。

测试数据位于 `.runtime/phase7-review-ui-1794323254053`、`.runtime/phase7-review/` 及报价探针要求的 `.runtime/phase4-ui-1794323395523`。端口使用临时端口、8796或8897，未使用正式8765。所有测试服务通过自己的 stdin 正常退出；没有结束正式服务。

### 验收探针问题及处理

- 首轮 Python 因未创建 `--basetemp` 的父目录产生 **269 passed / 163 setup errors**。错误全部为临时目录不存在；补建 `.runtime/phase7-review` 后完整重跑432项通过。[保留的初次日志](../output/playwright/phase7-review/pytest-initial-setup-error.log)。未修改测试预期或产品。
- 报价探针改为 `python -c` 启动后缺少 tests 模块搜索路径，启动失败；补入 `sys.path` 后上述专项通过。[初次日志](../output/playwright/phase7-review/quotes-initial-setup-error.log)。没有访问正式服务作为替代。
- 集成探针新增的独立回放显示检查首次在刷新任务尚忙时选择记录，导致等待结果超时；前三引擎计算已成功。确认刷新任务结束后再选择记录，完整重跑通过。[初次记录](../output/playwright/phase7-review/integrated-initial.json)。此处仅调整探针等待条件，未改产品。

## 截图与视觉检查

截图均由本验收聊天独立生成，目录 `output/playwright/phase7-review/`，使用人工测试数据。已实际查看以下截图，标题、数值、字段、状态和主要操作清楚可读：

- [320px资料导入](../output/playwright/phase7-review/phase7-materials-320.png)
- [320px条件编辑](../output/playwright/phase7-review/phase7-conditions-320.png)
- [320px AI配置](../output/playwright/phase7-review/phase5-ai-settings-320.png)
- [390px回测盈亏](../output/playwright/phase7-review/phase7-results-390.png)
- [1440px模拟结果](../output/playwright/phase7-review/phase7-paper-result-1440.png)
- [390px独立引擎结果](../output/playwright/phase7-review/phase7-external-result-390.png)
- [390px最新报价与估值](../output/playwright/phase7-review/phase4-quotes-390.png)

另保留各尺寸四工作区、转写、资料导入、数据错误、三引擎结果截图。长页面全页截图中的固定手机底栏会出现在截图时的视口位置；实际控件边界和滚动操作已由浏览器检查，未将全页拼接位置误判为页面固定遮挡。

## 源码与发布边界

验收前快照时间 **23:07:30 +08:00**；`app/frontend/tests` 共 **89个文件**的内容在独立回归前后保持一致，见 [source-before.json](../output/playwright/phase7-review/source-before.json)、[source-after.json](../output/playwright/phase7-review/source-after.json)、[source-stability.json](../output/playwright/phase7-review/source-stability.json)。没有读取或哈希正式数据库、`.env` 或用户Key。

源码基本验收通过，无待修复项。便携包构建、独立目录启动/退出、最终ZIP与源码对应关系、哈希、GitHub发布及PPT交接由协调聊天继续完成。若产品源码后续变更，应针对变更复验。本轮未新增真实供应商、真实ASR质量、实时券商或策略盈利能力，不用替身结果声称这些能力已通过。
