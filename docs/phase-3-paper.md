# Phase 3 — 免账号外部模拟引擎

协调：01a1c47c-e4ff-7033-8038-f30d94df465e。实现：01a1c47f-67ba-7bd1-87aa-bbc4acc88eb2。目录 C:/Users/Admin/Desktop/quant；非 Git，无 branch/worktree。状态：**本工作组实现完成，模块与浏览器通过；全量存在一项媒体测试失败，交协调与基本验收处理**。2026-11-10。

## 选择与范围

采用 **Backtrader 1.9.78.123 的真实 Cerebro / BackBroker**，已安装至项目 .venv。无需任何第三方账号、API key 或桌面交易框架。信号复用工作台已确认的组合规则；订单撮合、现金、持仓、费用由外部 BackBroker 实际执行，不把原撮合器改名。

比较：BackBroker 官方支持现金检查、持仓、佣金、市价单下一根开盘成交，适合单机历史回放。VeighNa PaperAccount 官方说明基于已连接行情接口，**不计算模拟资金，不持久化全部委托/成交**，且依赖 VeighNa 框架；本阶段不引入。其 MIT 许可证并不能补足上述产品能力。

Backtrader 使用 **GPL-3.0-or-later**（不是 MIT）；本地保留安装分发包的许可证原文及版本/来源。后续对外分发须按该许可证处理源代码及通知，不宣称可任意闭源分发。

本阶段明确是**历史研究模拟**，不提供实时接管、不连接券商、不注册账号、不下真实订单。先支持现有已校验的 raw 普通主板数据；复权研究数据须有明确契约并单独标为研究，不能直接当可交易价格。

回放采用固定数据与冻结组合，从初始状态重新执行到消费游标，输出取自真实 BackBroker；SQLite 事务中替换当前账本，稳定业务订单ID和请求ID去重。重启保守暂停。未提供增量模式，因此不存在把历史成交伪装成当前实时成交的入口，原模拟盘实际时钟约束保持原样。

官方依据：
- https://www.backtrader.com/docu/broker/
- https://github.com/mementum/backtrader
- https://pypi.org/project/backtrader/1.9.78.123/
- https://raw.githubusercontent.com/mementum/backtrader/master/LICENSE
- https://www.vnpy.com/docs/cn/community/app/paper_account.html
- https://github.com/vnpy/vnpy_paperaccount

## 接入检查点

接口契约见 phase-3-paper-api.md。独立文件 app/trading/paper_*.py、frontend/paper-external.{js,css}。协调负责主应用挂载和静态资源注册；本线程不修改现有核心交易模块。

2026-11-10 16:17（Asia/Shanghai）检查点：后端、前端独立区块均已落盘。前端可直接注册 `/static/paper-external.css` 与 defer `/static/paper-external.js`，自行追加 `#pex-panel` 至 `#workspace-paper`。不需要后台worker；按钮为创建、单步、运行至末尾、导出JSON。接口保持v1。原模拟账户启停与时钟逻辑不修改。

已执行引擎/服务检查16项通过，现金/订单来自真实BackBroker；Python 3.12出现上游 `datetime.utcnow` 弃用警告，未修改上游或隐藏警告。原手算测试预期已更正为90%目标仓位导致的100股再平衡（3笔成交、费用20.33、终值11629.67），不是省掉实际引擎调仓。

## 免费免账号行情独立探测

脚本 `scripts/paper_probe_feed.py` 只向腾讯公开HTTPS日线接口发单次请求，不携带账户、cookie或令牌，不写交易库。2026-11-10T08:17:12Z 实际HTTP 200，600000.SH未复权日线返回205根，实际2026-01-05至2026-11-10；响应SHA256为 `275a06688bb2852f60c8b14ad501269a6847e8f2b4d2597801f4c8ffcfbd74d2`。原响应及manifest存于 `.runtime/paper-feed-probe/`。

这仅证明公开历史接口可达；请求时北京时间16:17，最新当日日线未达到本项目18:00保守完成界限。返回OHLCV没有完整的官方每日限价、特殊状态与公司行为资料，因此**未自动导入严格模拟、未猜测限价、未称实时联调通过**。复权研究数据仍由数据工作组处理。新增外部模块可以消费用户已校验的未复权数据或显式演示数据，但当前没有开箱即用的免账号严格实时行情。

## 验证进度与待协调检查

- `scripts/paper_ui_smoke.py`：真实Chrome + 工作台主应用 + BackBroker，隔离数据目录。创建已确认测试组合、未复权演示CSV，经页面创建回放、单步、运行至末尾、导出JSON、刷新恢复；320/390/1440无横向页面溢出，0 console/page errors。3笔成交、终值11629.67、费用20.33，与手算一致。原paper列表仍空，未写入正式数据。输出 `output/playwright/paper-external-{320,390,1440}.png`、`paper-external-result.json`、`paper-external-export.json`，日志 `.runtime/paper-evidence/browser.log`；已实际查看390截图。
- 扩充撤单通知回归后本模块17项通过。BackBroker撤单通知下一根才送达，适配器现保存实际撤单日，避免历史订单日期被下一根改写；先复现为1 failed，再修复。
- **全量首次171项：170 passed、1 failed**，`.runtime/paper-evidence/full-pytest.log`。失败为非本线程文件 `tests/test_media_fetch_validation.py::test_batch_deadline_counts_remaining_samples`：测试设30ms整批期限但预期至少启动一次；实际初始化已耗尽期限，三项均not_run。随17项模块测试重跑时仍出现同一失败。此项需协调/基本验收记录，本线程不越权修改媒体验证文件。不得把全量首次结果宣称全绿。
- 最终已补缺可选包时503且不建会话、并发重复request_id只消费一次。**本模块19项均通过**；全量最终 **173 passed、1 failed、104上游弃用警告，52.71s**，`.runtime/paper-evidence/full-pytest-final.log`。唯一失败仍为上述媒体期限用例，未出现模拟盘/研究数据/原工作台回归失败。
- 媒体用例在完全不导入paper模块的新进程中独立运行仍失败；实测其 `environment()` 用时214.762ms，超过测试30ms总预算（初始化本身已耗尽时间），见 `.runtime/paper-evidence/media-deadline-diagnosis.json`。不修改此非本线程拥有的媒体脚本/测试；留给协调明确安排后续。
- `compileall`（3个后端模块、2个脚本）与 `node --check frontend/paper-external.js` 通过。测试端口8894已无监听，无残留本次浏览器服务。上游 `datetime.utcnow` 弃用警告如实保留，不影响已验证的计算结果；没有修改或掩盖上游代码。

## 最终交接

1. 已安装免费免账号Backtrader 1.9.78.123，原文许可证与版本/来源在 `licenses/`。独立可选依赖 `requirements-paper.txt`；没有安装VeighNa桌面框架。
2. 真正调用Cerebro/BackBroker处理订单、现金、持仓、佣金与滑点；仅复用既有用户组合信号及费用公式。独立kind=`paper_external`、冻结组合/数据hash/引擎版本、事务去重、重启保留；未改原engine/service/store等共享文件。
3. 工作台独立区块已完成，并由界面线程注册资源、协调挂载路由。可创建、单步、运行至末尾、查看现金/权益/收益/回撤/持仓/信号/订单与原因、导出JSON；公开响应不含内部去重状态。
4. 能力边界：仅历史回放，暂无外部免账号实时跟盘；复权股票池不进入该撮合器，真实数据未补造限价或公司行为资料。原本地增量模拟和实际时钟防回填保持现有逻辑。
5. 本工作组未碰正式策略、会话或8765服务；仅隔离数据与端口验证。没有额外聊天或后台代理。基本自查对照用户需求、主流程与明显回归，未扩展为对抗审计。

本工作组范围内无待实现代码；阶段最终接受以及媒体测试跟进由可见协调/基本验收线程记录。
