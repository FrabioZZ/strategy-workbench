# Phase 4 免费报价与模拟估值实施报告

日期：2026-11-10（Asia/Shanghai）。实现聊天：`01a1c535-301f-7dd0-ad55-031b37989908`。范围：`docs/phase-4-plan.md` Task 1。工作目录 `C:/Users/Admin/Desktop/quant`，非 Git，无 branch / worktree。

**Task 1 实施与自测完成，交独立基本验收；尚未部署新后端。** 最终全量 **211 passed / 104 条既有 Backtrader 弃用提示 / 69.69s**；隔离 Chrome 主流程通过。正式 8765 未重启，正式库未写入测试策略、模拟账户或报价。

## 实现结果与文件

| 文件 | 责任 |
|---|---|
| `app/trading/quotes.py` | 腾讯 HTTPS 批量快照、严格代码/数值/源时间解析、2026交易日历、源与缓存状态、共享缓存和退避 |
| `app/trading/quote_accounts.py` | SQLite 只读持仓快照、单账户估值、独立45秒后台线程 |
| `app/trading/quote_router.py` | 报价股票池和报价/估值只读 API |
| `app/main.py` | 创建共享服务、路由、生命周期启停；原 PaperWorker 15秒调度不变 |
| `frontend/quotes.js/css` | 模拟盘同页独立报价区、股票搜索、手动/自动刷新、逐账户估值、故障/现金空仓状态 |
| `frontend/index.html` | 注册报价静态资源 |
| `frontend/trading.js` | 明确原日线撮合与新快照估值的边界，不再笼统声称整个页面无盘中报价 |
| `tests/test_quotes.py`、`tests/test_quote_api.py` | 33项确定性服务/API测试 |
| `tests/quote_ui_server.py`、`scripts/phase4_ui_smoke.cjs` | 明确人工报价/时钟/持仓的隔离浏览器验证 |
| `scripts/probe_free_quotes.py` | 三标的、8秒超时的真实公网探测与原始证据保存 |

原 `service.py / engine.py / paper_engine.py / paper_service.py / worker.py` 未修改。公开快照不生成 dataset，不调用 `sync`、`advance` 或下单逻辑；未增加盘中自动策略交易。

## API 合同

两个接口都是本机 `GET`，无第三方账户或密钥，响应沿用应用 `Cache-Control: no-store`；源端共享缓存位于服务内部。

### `GET /api/trading/quotes/catalog`

返回 `members: [{symbol,name}]`、`universe`（含成员快照日期）、`source`、`message`。从最新已导入研究数据集的 `symbol_metadata` 取得现有股票池；SQL只提取元信息，不把20万行研究行情传给浏览器。正式库既有沪深300为300只。没有股票池时仍可直接输入如 `600000.SH` 的完整代码，无需CSV/Tushare/策略。

### `GET /api/trading/quotes/overview?symbols=000001.SZ,600000.SH`

- 页面指定至多10个沪深A股代码；格式为 `6xxxxx.SH` 或 `0xxxxx.SZ / 3xxxxx.SZ`。错误代码返回400，超长查询参数由FastAPI返回422。
- 顶层：`quotes`（仅请求选股的报价）、`accounts`（所有增量模拟账户的独立估值）、`excluded_historical_accounts`、`server_time`、`refresh_seconds:45`、`source`、`market`。
- 报价：`symbol/name/price/previous_close/change/change_pct/volume_lots`；`source_time`（供应商快照时间）、`received_at`（该有效解析快照收到时间）、`last_attempt_at`、`last_success_at`、`next_attempt_at`；`source`、`security_status`、`feed_status`、`freshness`、`valid_for_valuation`、`error`、`market`。时间均带 `+08:00`，UI明确北京时间。
- `feed_status`: `ok / waiting / error`，与报价新鲜度分离。新鲜度为 `fresh / closed_latest / break_latest / stale / stale_cache / calendar_unknown / status_unknown / invalid_time / unavailable`。源出错保留旧价和旧的源/收到/成功时间，更新尝试和错误；`valid_for_valuation=false`。
- `market`: `phase`（交易/竞价/午休/闭市/盘前/日历未知）、`expected_date`、时区、日历起止和官方链接。
- 每账户：`id/name/mode/execution_status/cash/ledger_cursor/portfolio_revision/valued_at`，`status: cash_only / valued / incomplete`，`complete`、`positions`、`market_value/total_assets/unrealized_pnl`。每个持仓含实际股数、账面均价、账面成本、有效市值、浮盈亏及完整 `quote`。
- 总资产＝现金＋现价×实际股数；浮盈亏＝市值−数量×账面均价。费用沿用原账本成本；不重复扣除历史费用。现金空仓的市值和浮盈亏为0，总资产等于现金。任一持仓无有效报价时，完整总资产/总市值/总浮盈亏为 `null`，现金和各持仓成本仍可查看；账户之间不求和。
- 仅 `kind=paper && mode=incremental` 进入最新估值；历史回放和所有 Backtrader 账户只计入排除数量，绝不改身份或自动转换。

## 缓存、后台与时间判断

- 正常单标的请求间隔45秒，批次至多50个代码，全源最短批次间隔2秒；新代码也受全源限制。多账户、多标签、手动刷新和后台共用一个 `QuoteService`，互斥合并重叠请求，不能靠刷新按钮绕过限流。每轮先处理最久未尝试的代码，超批次者明确等待。
- HTTP读取超时8秒，响应最多256KiB；只用标准库，不增加 AKShare 或其他行情依赖。源失败/无有效返回时全源退避；单标的失败也独立退避，依次45/90/180/300秒，上限300秒。缓存最多1500条，重启后重新获取，不将旧内存价伪装为新价。
- 页面可见且位于模拟盘时，每45秒请求一次；隐藏页面或离开模拟工作区停止页面轮询，返回即刷新。手动请求遵守同一缓存策略。
- 后台独立线程每45秒读取所有增量账户现有持仓（包括暂停账户，仅估值），及最近120秒页面关注过的股票。后台读取不会续订关注期限。页面关闭后持仓继续刷新，关注股票过期后停止；无持仓、无关注时不请求源。退出本地服务后停止。
- 账户读取使用 SQLite `mode=ro` 连接，并在联网前关闭；测试在 transport 执行期间以独立连接成功执行 `BEGIN IMMEDIATE`。后台没有交易服务写入口。
- 源时间与接收时间相互独立。错代码、重复代码、零价/无效昨收、非有限值、无效/未来源时间、已知非交易日时间或时间倒退均不作为有效新报价。零成交只显示“零成交，状态未知”，不宣称停牌，停止有效估值。
- 盘中源快照超过180秒为过期；接收缓存超过180秒也停止有效估值。午休要求同日11:28以后的快照；盘后/盘前/休市要求最近已知交易日14:58以后的快照。2分钟收盘/午休容差用于公开源边界延迟；源时间不被改写为15:00。实际探测源返回16:14～16:15的供应商快照，原样保留。
- 日历依据 [上交所2026年休市安排（2025-12-22）](https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml)，2026全年的周末及公告假期均闭市，包括春节、国庆长假。区间以外或无法定位上一交易日时，明确“日历未知”，停止有效估值；不按自然日龄误判长假。

## 真实网络证据

本机执行 `.venv/Scripts/python.exe scripts/probe_free_quotes.py`，退出0。请求 `https://qt.gtimg.cn/q=sh600000,sz000001,sz300750`，HTTPS 200；2026-11-10 **19:27:30.281+08:00** 请求，**19:27:32.010+08:00** 收到1580字节。GB18030解码，每条88字段。

| 标的 | 现价 | 昨收 | 源快照时间（北京时间） |
|---|---:|---:|---|
| 600000.SH 浦发银行 | 10.20 | 10.10 | 2026-11-10 16:14:59 |
| 000001.SZ 平安银行 | 11.86 | 11.89 | 2026-11-10 16:15:00 |
| 300750.SZ 宁德时代 | 249.95 | 248.64 | 2026-11-10 16:14:45 |

证据目录 `.runtime/phase4-quote-probe/`：`probe.json` 保存URL、请求/收到时间、HTTP状态/头部和摘要；`response.bin` 原始字节；`response.txt` 解码原文；`parsed.json` 使用产品解析器、以原收到时刻评价所得 `closed_latest / valid_for_valuation=true`。原始SHA256：`d16b1afb8af429a5b23a14d755ebb935884ccb0fcbe4c0437730f322680416ce`。

**这是闭市真实可用性探测，未现场观察盘中持续跳价。** 浏览器动态价格、故障与持仓均是明确人工测试夹具，不能替代盘中市场实测。公开接口没有稳定性承诺；故障时展示源状态并保守停止完整估值。

## 验证与证据

pytest 均通过 `subprocess.run(..., timeout=120或180)` 的有界子进程，使用唯一 `.test-tmp/phase4-*`，不使用正式数据库。本次 TestClient 在沙盒内实际通过。浏览器本身160秒 watchdog，使用独立8898端口与 `.runtime/phase4-ui-*`；最终重跑使用已获自动批准的 `require_escalated`，以清理本脚本创建的进程树。

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 产品模块实现前运行 `pytest -q tests/test_quotes.py` | 缺少 `app.trading.quotes`，退出2，确认功能尚不存在 | `.runtime/phase4-tests/red.log` |
| 初始纯服务测试 | 28 passed，0.49s，退出0 | `green-first.log` |
| API独立测试 | 2 passed，2.08s，退出0 | `api-first.log` |
| 扩充后目标测试 `pytest -q tests/test_quotes.py tests/test_quote_api.py` | 33 passed，2.44s，退出0 | `targeted.log` |
| 首轮全量 `pytest -q -p no:cacheprovider --basetemp=.test-tmp/phase4-full-<uuid>` | 211 passed，104既有警告，66.91s | `full.log` |
| 最终全量同命令，独立新basetemp | **211 passed，104既有警告，69.69s，退出0** | `full-final.log` |
| 首轮隔离 Chrome 主流程 | 实测自动刷新44.975秒，三宽度通过，0浏览器错误 | `.runtime/phase4-ui-1794310453330/result.json` |
| 基本复核新增连接故障回归，修复前 | 503后切换账户，错误重新展示旧完整估值，断言失败退出1；已观察此失败 | `.runtime/phase4-ui-1794310650249/server.log`；失败断言位于浏览器脚本本地连接故障段 |
| 同回归修复后完整浏览器重跑 | **通过，44.985秒真实定时刷新；0非预期错误，1次显式注入503；退出0** | `.runtime/phase4-ui-1794310746637/result.json`、`server.log` |
| JS语法与Python编译 | `node --check frontend/quotes.js`、`node --check scripts/phase4_ui_smoke.cjs`、目标Python compileall，均退出0 | 本线程工具输出 |

全量涵盖原资料、严格回测/历史回放、日线时钟修复、研究回测及真实 Backtrader 引擎测试。104条提示均来自既有 Backtrader `datetime.utcnow()` 弃用，不是新增失败。

浏览器命令：

```powershell
$env:NODE_PATH='C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
node scripts/phase4_ui_smoke.cjs
```

浏览器覆盖：无股票池直接代码报价；无策略/账户不制造策略；300只股票池、名称搜索和选择；手动缓存；真实45秒自动刷新；持仓成本/现金/浮盈亏计算；现金空仓；历史排除；源故障及恢复；本地API失败及账户切换；刷新前后完整账本一致；离开工作区不轮询；可控 `document.hidden` 事件验证隐藏/返回分支（后两项用浏览器时钟加速，不冒充45秒实测）；320/390/1440无水平溢出。

截图：`output/playwright/phase4-quotes-{320,390,1440}.png`，实际查看了320和1440。窄屏整段截图含固定底部导航，导航覆盖位置随实际页面滚动变化；页面不横向溢出。最终机器报告同时保存为 `output/playwright/phase4-result.json`。

## 基本复核、执行裁定与交接

- 使用 executing-plans、TDD、verification-before-completion；浏览器沿用项目已有 Playwright 模块脚本方式。读取设计、计划、Phase3索引、README和Phase2修复；没有重新申请设计/流程批准。
- Ruling：按用户指定单一实现线程，不创建代理/聊天、不向父/旧聊天发消息。非Git环境不运行技能Git辅助脚本；本报告作为执行账本，最终独立基本验收由协调安排。
- 基本复核发现本地连接错误后的账户切换可能重显旧估值：先加浏览器断言并观察失败，再增加独立 `disconnected` 状态，错误期间所有账户切换均保持不可估值，成功响应后才恢复。没有做额外对抗审计。
- 首轮浏览器功能通过但沙盒拒绝清理测试进程，未把清理当成功：按精确 `quote_ui_server.py` 与测试目录识别本次进程，经批准后清理；脚本增加清理失败报告，最终沙盒外运行退出0并清理自己的树。未停止正式进程。没有自动审批拒绝遗留。
- 正式交易库在开始只读核对为一个300只203572行研究数据集，无策略/回测/模拟；结束只读仍 `dataset=1`。资源正文SHA256为 `61758b4dd2c18fc82ce419922f14d1366100b78292fc57bab1d6ec2570fc2469`；证据 `.runtime/phase4-tests/production-readonly.json`。测试始终使用隔离库。
- Task 1：complete（实现、目标/全量测试、浏览器、真实源探测和报告齐全）。未改协调拥有的Phase4索引/设计/计划和README。**Task 2 独立验收、Task 3 正式备份/重启由协调继续**；正式进程尚未加载新API，部署后才能声称正式报价服务上线。
