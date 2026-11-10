# Phase 3 — 沪深300研究界面与模拟入口

- 协调线程：`01a1c47c-e4ff-7033-8038-f30d94df465e`。
- 本线程：`01a1c47f-fca6-7be3-9fa9-eeb87e24bb0f`，目录 `C:/Users/Admin/Desktop/quant`；非 Git，无 branch/worktree。
- 独占：`frontend/index.html`、`frontend/trading.js`、`frontend/trading.css`、`scripts/phase3_ui_smoke.cjs`、本记录。不会改后端、正式策略或账本。
- 用户已授权直接实施既定范围；沿用 Phase 2 风格与四模块，不重新发起设计审批或创建聊天/后台代理。

## 实施与验收计划

1. 分开沪深300复权研究和严格 CSV 两条回测路径；已保存策略是唯一执行来源，无策略时引导创建。
2. 读取数据线程的 `docs/phase-3-data-api.md` 后接入批量目录与名称/代码搜索。显示实际覆盖、股票池快照、来源、抓取时间、缺失与存活偏差，不自行编造状态或能力。
3. 读取 `docs/phase-3-paper-api.md` 和独立资源后注册模拟入口；保留旧本地模拟路径。
4. 真实后端配隔离 `DATA_DIR` 完成主要浏览器流程、320/390/1440 布局、console 检查；人工构造行情仅在隔离环境中标记用于验证。

## 状态

- 已核对 Phase 2 前端与 API、原 smoke 测试及本地测试服务器。
- 数据 API 已落盘并接入：复用原 `/datasets`、`/backtests`，根据 `research_adjusted` / `adjusted_research` 分流，原纸面模拟下拉排除研究数据。实现整池一个选项、名称/代码搜索、分页显示、逐股日期、来源/快照/抓取/完整性和研究结果快照。
- 外部模拟 API 和独立资源已核对，`index.html` 已注册 `/static/paper-external.css` 与 defer `/static/paper-external.js`，原模拟页页首提供直达按钮。外部区块嵌在原四模块中，不使用外链/iframe；没有修改模拟工作组独占资源。
- 第一轮 `scripts/phase3_ui_smoke.cjs` 已 exit 0：隔离真实交易 API，无策略空状态不会创建策略；300只人工测试股票单数据集、名称/代码搜索与失败标的、研究虚拟份额回测、持久化历史、严格 CSV 回测、原模拟单步启动同步暂停、320/390/1440 布局、0 browser console/page errors。
- 人工测试研究结果：1001 初始计价单位，100.1 虚拟份额，两笔调仓，收益20%；明确仅为验证算法和UI的人工构造数据，不是真实市场业绩。
- 第一轮证据 `output/playwright/phase3-result.json`，目录 `.runtime/phase3-ui-1794298473458`；已人工查看 390/1440 研究页截图。测试首次因 Windows stdin 默认编码失败，已改二进制 UTF-8 JSON 读取，后续通过。
- 当前前端实现与隔离浏览器主流程已完成；真实公网数据仍在数据线程抓取，正式数据导入和阶段最终接受状态由协调线程及独立可见基本验收确定。

## 最终集成与验收

- 对照真实 `app/trading/history.py` 元数据补充 `complete_observed_calendar` 中文说明、逐股缺失天数/内部缺口/尾部覆盖提示；日历只称“已核实日历截止”，不冒充官方未来日历。失败条目显示供应商实际 error，未知计数不假报为零。
- 研究结果保存和读取冻结数据快照、策略版本、实际区间与价格口径；数量为可分割虚拟份额，现金/净值为研究计价单位，绝对价格阈值在选择时提醒复权尺度。停牌/缺口/未来信息及股票池存活偏差在选择和结果处可见。
- 旧 CSV 与原回放数据筛选已按最终 `allowed_modes: [backtest,replay,incremental]` 契约修正。联调曾因把模式名写成 paper 隐藏合法 CSV，完整 smoke 先失败，修复后通过。
- 最新完整验收命令：设置 `NODE_PATH=C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`，使用同 runtime 的 `bin/node.exe scripts/phase3_ui_smoke.cjs`。本机 Chrome、测试端口8768、`tests/ui_server.py`、隔离 `.runtime/phase3-ui-1794298801495`；**exit 0，console/page errors 为0**。
- 主流程覆盖：无数据/无策略不灌示例；300股票一批数据、名称/代码搜索、更多结果、失败股禁选、逐股缺口；真实研究引擎运行/历史恢复；严格 CSV 导入/旧回测；原本地模拟的单步、启动、同步、暂停；真实 Backtrader 创建无成交、单步、运行到末尾、导出JSON、页面刷新后重新选择完成账本；320/390/1440px四模块无整页横向溢出。
- 本次 Backtrader 为 `Backtrader BackBroker 1.9.78.123`，8根人工行情产生1笔实际引擎模拟成交。研究fixture为两笔虚拟调仓。两者都是隔离人工行情测试，不代表真实市场收益或实时接入。
- 最新证据：`output/playwright/phase3-result.json`、`phase3-external-ledger.json`、`phase3-mobile-research.png`、`phase3-320/390/1440-backtest.png`、`phase3-320/390/1440-paper.png`。已人工检查320模拟页和390研究结果，以及此前390/1440研究页；股票结果列表限制为可滚动区域，避免300只股票把执行表单推到页面底部。
- 最终 `node --check frontend/trading.js` 与 `node --check scripts/phase3_ui_smoke.cjs` 均 exit 0；仅在完整smoke之后微调计价单位/股票数量中文标签，未更改执行逻辑。

## 交接边界

- 未触碰正式8765服务、正式策略、正式账户与账本，也没有生成正式示例策略。测试脚本拒绝8765端口；行情和规则均只写入独立测试目录。
- 严格CSV导入保留原明确核验条件；沪深300研究入口不复用官方限价/无公司行为确认。原模拟和Backtrader都排除复权研究数据。
- Backtrader只提供历史回放，不能因公共历史接口可访问而宣称严格实时行情已接通。真实股票池日期、抓取来源、实际截止和覆盖均从最终导入记录渲染，无硬编码“成功到2026-11-01”。
- 未做对抗审计。后续独立基本验收如发现问题，应留在本阶段可见工作组闭环。
