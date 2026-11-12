# Phase 11 · 首版演示基本验收

## 准备状态

2026-11-11，复用 `C:/Users/Admin/Desktop/quant` 的 `main`，准备时 HEAD 为 `089e71a`。当前检出包含 Phase 9/10 基线及并行实施改动。由协调聊天 `01a1ca9e-da28-7a61-9ddf-3a293c56455d` 通知开始正式点按。按 [AI 实施说明](phase-11-ai.md) 和 [演示启动说明](phase-11-demo.md) 核对实际入口、样例文本、股票、日期和预期结果。

README 的 Windows 源码入口为 `powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Port <端口>`，调用 `scripts/run.py`，按 `DATA_DIR` 加锁并绑定 `127.0.0.1`。`workspace.sqlite3`、`trading.sqlite3` 及模型设置都位于该数据目录。使用演示说明指定的启动命令，开新隔离目录并记录最终路径。若需要单独运行无模型、无行情检查，另用全新的隔离目录及空闲端口。设置 `PYTHON_DOTENV_DISABLED=1` 并清除子进程继承的 `AI_PROVIDER`、`AI_BASE_URL`、`AI_MODEL`、`AI_API_KEY` 和 `TUSHARE_TOKEN`，通过 `GET /api/status` 确认模型未配置。正式 `data/`、原有服务及账本不参与。

本机已有 Python 3.12.14、FastAPI 0.162.2、Uvicorn 0.54.0、Node v24.14.0、仓库安装的 `playwright-core` 和 Chrome。已验证本机可监听 `127.0.0.1` 的临时 TCP 端口。正式验收用 Chrome 访问独立启动的本机服务，观察实际请求和响应。模型替身在模型边界运行，并明确标注。

| 准备命令 | 结果 |
| --- | --- |
| `node --test tests/test_market_workstation_ui.cjs` | 1 项通过，覆盖图表、指标勾选及模拟会话刷新。浏览器 HTTP 由夹具响应。 |
| `node --test tests/test_phase10_mapping_ui.cjs` | 1 项通过，覆盖手工澄清、重试及显式确认。浏览器 HTTP 由夹具响应。 |
| `./.venv/Scripts/python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp <全新的 .runtime 子目录> tests/test_workstation.py tests/test_phase10_mapping.py -k 'not test_workstation_endpoint_runs_historical_interval_without_dataset_input and not test_user_resolution_is_versioned_and_required_for_linked_portfolio'` | 7 项通过，2 项跳过选择。默认临时目录无法创建 `tmp_path`。改用工作区临时目录后，整组在前三项通过后停滞并已中止，因此单独完成了不含 `TestClient` 的这 7 项。实际 HTTP 留给正式点按。 |

## 正式点按检查点

| 检查点 | 页面操作及通过依据 |
| --- | --- |
| 启动与隔离 | 按演示说明启动。记录启动命令、端口、隔离目录和 `GET /api/status`。浏览器打开 `http://127.0.0.1:<端口>/`，核对演示模型、样本行情与模拟结果的标识。 |
| 资料一键 AI 决策 | 在「资料」按演示说明导入样例文本，点击 Phase 11 一键入口。等待任务完成，核对可执行草案的原文引文、采用的定义或数值、采用理由。检查未确认时组合仍未就绪。 |
| 原文保护 | 使用含明确买卖方向、数值、周期、标的和交易例外的文本，核对规则及决议与原文逐项一致。若规则超出引擎能力或条件冲突，页面保留待确认项并说明原因，无法借一键入口生成可执行规则。记录所用的原文和页面显示的规则或提示。 |
| 确认并保存 | 从资料进入「策略组合」，检查规则、来源版本与决议。按正常入口最终确认并保存。刷新后核对组合仍可选、版本与规则一致。记录实际保存响应和组合版本。 |
| 工作台回测 | 在「回测」选择已保存版本、样本股票、开始/结束日期和初始资金，点击「运行回测」。核对样本标识、可见 K 线及成交量、信号和成交记录。检查一笔信号与下一根开盘成交的时间关系。核对实际 `POST /api/trading/workstation/backtests` 响应及保存结果。 |
| 工作台历史模拟 | 在「模拟盘」用同一组合版本和样本区间启动历史模拟。检查 K 线、信号、成交及独立模拟会话。核对 `POST /api/trading/workstation/paper/sessions` 响应的历史模式和同口径成交，刷新后能找回该会话。 |
| 旧人工路径 | 在「策略组合」从「可用草案」加入组合，使用条目内「AI 生成执行参数」，选择判定口径并点「应用选择并校验」。核对证据，勾选确认并「保存组合版本」，检查就绪状态。另在无模型实例检查「添加手工策略」。 |
| 版本失效 | 若采用的口径经人工改选，核对采用值和理由更新并重新确认。主流程完成后编辑原文并保存，检查旧草案或映射标记过期，旧链接规则不能再次确认或启动新执行。确认已完成的回测或模拟仍能查看冻结结果。 |
| 无模型与无行情 | 无模型实例仍可导入资料，模型动作给出可理解的配置提示。无覆盖行情时运行有效组合，工作台说明缺行情，页面无虚构 K 线、信号或成交。 |
| 明显回归 | 桌面端切换「资料」「策略组合」「回测」「模拟盘」，核对无阻断的页面异常。至少在移动宽度复核图表和买卖记录，检查溢出及基本操作。 |

## 正式实测 · 2026-11-11

- 在 PowerShell 检出目录使用 `& .venv/Scripts/python.exe -B scripts/run_demo.py --port 0`，Chrome 通过仓库已有 `playwright-core` 操作页面。验收实例为 `http://127.0.0.1:63119/`，隔离账本为 `.runtime/phase11-demo-zf04y1ka`。`GET /api/status` 返回 200，模型为 `phase-11-demo-fixture`。启动时资料、组合、回测、历史模拟列表均空。验收进程已停止。
- 「载入示例文本」返回 201，「提取策略」返回 202 并完成。原文为 `600000.SH，日线。`、`收盘价站上5日均线且放量时买入。`、`收盘价跌破5日均线时全部卖出。`、`目标仓位20%。`。浏览器标明使用本机固定模型替身，提取后四段原文与导入时一致。旧「生成执行规则 · 人工选口径」返回 200，显示两项待人工选择，确认框禁用。
- 点击「让 AI 补全并生成执行规则」，`POST …/mapping/complete` 返回 200。保留 600000.SH、日线、5 日均线、买卖方向和 20% 目标仓位。页面逐项展示原文、采用值和理由。将「站上」解释为由下向上穿越，避免持续在均线上方时反复触发。将「放量」解释为当日成交量严格大于此前 20 根日线均量的 1.5 倍，因为原文未给阈值。两项均标记为「AI 假设」。确认框默认未勾选，组合列表仍为空。勾选确认后保存返回 201，组合 v1 就绪。
- 用 v1、600000.SH、初始资金 100,000 元运行 `2025-11-03` 至 `2025-11-28`。`POST /api/trading/workstation/backtests` 和 `POST /api/trading/workstation/paper/sessions` 均返回 201。两份结果各 20 根日线、20 条逐日信号记录、2 笔模拟成交，均显示「演示行情」并注明「Phase 11 合成样本日线」。K 线、成交量、均线和量比可见，量比可关闭及重新开启。历史模拟显示已结束。390px 下无页面横向溢出，刷新后从「模拟记录」可重新打开结果。回测 ID 为 `3eef9af53ad2428c9f4998da4fda010f`，历史模拟 ID 为 `5d945566d2c7488fbdc891f7c532402a`。[实际 Chrome 回测截图](../output/playwright/phase-11-acceptance/phase-11-backtest.png)

| 方向 | 信号日 | 下一交易日开盘成交 | 数量 | 成交价 | 费用 |
| --- | --- | --- | ---: | ---: | ---: |
| 买入 | 2025-11-17 | 2025-11-18 | 1900 股 | 10.35 元 | 5.90 元 |
| 卖出 | 2025-11-21 | 2025-11-24 | 1900 股 | 10.20 元 | 15.50 元 |

- 「人工调整口径」把量比改为 20 根均量的 2 倍，`POST …/mapping` 返回 200 并生成新映射版本，页面标为「人工选择」且清除确认勾选。旧组合新发起回测返回 409，提示载入并确认最新执行规则。重新勾选后 `PUT …/portfolios/{id}` 返回 200，保存为 v2。再把原文仓位从 20% 改为 25%，`PUT …/transcript` 返回 200，原文为 v2，资料标记「草案已过期」并隐藏一键补全入口。保存的 v2 组合再次发起回测返回 409。历史回测仍可通过 GET 200 读取原 v1 映射与原有成交。
- 普通入口使用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Port 8879`，`DATA_DIR` 为 `.runtime/phase11-empty-8879-E9nYmW/data`。禁用 `.env` 并清除子进程继承的模型与 Tushare 配置。Chrome 在 `http://127.0.0.1:8879/` 验证 `/api/status` 返回 200 且模型未配置，文本导入 201，提取请求 202 后显示「AI 未配置」和设置指引。手工新增日线价格阈值策略，买入阈值 10、卖出阈值 12、仓位 25%，显式确认保存返回 201，刷新后组合 v1 仍就绪。
- 普通实例用上述手工组合对 `600000.SH` 点按回测和历史模拟。`2025-11-03` 至 `2025-11-28` 均返回 400 并提示未配置 `TUSHARE_TOKEN`。`2025-11-08` 至 `2025-11-09` 均返回 400 并提示「所选股票与日期没有可用行情」。四次都没有生成 K 线、信号、成交或历史记录。Chrome 无页面异常或请求失败，验收后确认 8879 已停止监听。[无模型和无行情证据](../.runtime/phase11-empty-8879-E9nYmW/evidence.json)
- 定向回归通过 41 项，覆盖明确的买卖方向、周期、数值、标的、交易例外及版本失效。另在新隔离 SQLite 库直接调用注册的映射处理函数，11 组场景通过，包括含未支持例外、明确量比冲突、标的证据不符、5 分钟周期、模型输出额外仓位字段或无效方向、回答不完整、模型完成前原文变化。固定演示替身仅接受指定样例，这些边界使用定向夹具验证。已有人工映射和资料流程的浏览器回归 4 项通过，使用接口夹具。
- 对正式 `data/` 的 `workspace.sqlite3`、`trading.sqlite3`、现有 `workspace.sqlite3-wal` 和 `workspace.sqlite3-shm` 做启动前后只读文件检查，大小、修改时间和 SHA-256 一致。验收使用独立端口及隔离目录。

实测请求见 [服务日志](../output/playwright/phase-11-acceptance/server.log)。浏览器和定向回归命令如下，`--basetemp` 每次取全新目录。

```powershell
node .runtime/phase11-acceptance-live.cjs
node .runtime/phase11-empty-acceptance-8879.cjs
node --test tests/test_phase10_mapping_ui.cjs tests/test_phase11_mapping_ui.cjs tests/test_transcription_ui.cjs
& .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.runtime/phase11-acceptance-source-protection/pytest `
  tests/test_phase11_mapping_versions.py tests/test_phase10_terms.py `
  tests/test_phase10_mapping.py::test_daily_terms_cannot_clear_an_unmapped_trading_exception `
  tests/test_phase10_mapping.py::test_five_minute_input_stays_out_of_daily_mapping `
  tests/test_ai_backend.py::test_unsupported_or_unproven_mapping_is_never_ready `
  tests/test_ai_backend.py::test_explicit_dual_ma_maps_but_reversed_buy_sell_does_not `
  tests/test_ai_backend.py::test_mapping_cannot_drop_unextracted_financial_filter `
  tests/test_ai_conditional_mapping.py::test_conflicting_time_or_units_cannot_be_erased
& .venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.runtime/phase11-acceptance-http-tests `
  tests/test_phase11_ai_completion.py `
  tests/test_phase10_mapping.py::test_user_resolution_is_versioned_and_required_for_linked_portfolio `
  tests/test_app.py::test_unconfigured_failure_is_saved_and_retryable `
  tests/test_workstation.py::test_workstation_endpoint_runs_historical_interval_without_dataset_input
```

## 发现与限制

- **非阻断界面问题**。实际 Chrome 报告 CSP 拦截 `market-workstation.js` 中通过内联 `style` 设置的 `--series-color`，影响图表指标菜单色样与读数文字配色。K 线、指标曲线、信号标记和成交表均可见，图表指标勾选正常。需修复色样与读数配色后复查浏览器控制台。验收未改产品代码。
- **非阻断文案问题**。普通历史回测和历史模拟在工作日缺行情配置时显示「未配置TUSHARE_TOKEN，等待导入增量CSV」，沿用了增量跟盘的措辞。空白区间能明确提示没有可用行情，两个路径均拒绝创建结果。
- 受限执行环境的 Windows 回环连接使首次演示启动无 HTTP 响应，标准 `TestClient` 也在 `socket._fallback_socketpair` 阶段停滞。换到本机可用回环连接后完成真实 HTTP 验收，补跑的 11 项 `TestClient` 回归全部通过。
- 范围为首版隔离日线演示的正常用户工作流。未验证真实模型质量、真实行情接入或盘中交易表现。

**验收结论**。首版演示主流程、显式人工确认、版本保护及缺配置处理通过。记录两项非阻断的界面与文案问题。

## 修复复验 · 2026-11-11

修复聊天 `01a1cabf-7ad4-70f2-890e-9e5290ba8949` 完成以下复验，两项问题关闭。

- `node .runtime/phase11-csp-readonly.cjs` 实际访问 `8766` 的已保存回测，34 个色样和 34 条读数均匹配曲线的六色配色，控制台相关 CSP 拦截为 0。`style-src 'self'` 继续生效。
- `node .runtime/phase11-feed-copy-check.cjs` 在全新隔离实例实际验证普通历史回测和历史模拟。缺配置和覆盖行情时均返回 HTTP 400，页面提示配置 `TUSHARE_TOKEN` 或导入覆盖日期的未复权日线 CSV，账本无新记录。实时增量会话返回 HTTP 201 后显示增量 CSV 提示。实时公开报价使用空响应夹具。
- 工作台、行情和分钟模块的 27 项专项回归通过。协调复跑 Python 全量 551 项、浏览器回归 5 项均通过，正式账本未参与。
