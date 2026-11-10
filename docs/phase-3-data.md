# Phase 3 — 沪深300真实历史研究数据

工作目录 C:/Users/Admin/Desktop/quant；非Git，无branch/worktree。协调线程 01a1c47c-e4ff-7033-8038-f30d94df465e。

状态：**实现、真实批量取数、隔离导入和API验证完成，等待协调正式备份/导入/重启及阶段基本验收**。原严格模式仅普通主板且无公司行为，不能直接导入整个沪深300；已新增隔离的复权研究模式，契约见 phase-3-data-api.md。禁止用于模拟盘，旧严格API保持兼容。

## 实测历史记录（最终结果以上文为准）

- BaoStock 0.8.9 官方PyPI包，匿名 bs.login，经沙盒内和获准沙盒外各实测，TCP接收超时，error_code=10002007。官网页面空白与TCP结果分开记录；没有仅凭官网不可用就放弃。data/history/probe/login.json 保留沙盒外失败。
- 改试腾讯公开历史HTTP接口（AKShare官方文档 stock_zh_a_hist_tx 所用来源），600000.SH真实样本返回到2026-10-30；单次全区间最多640行导致2024年初截断，已改年度分段。
- 2024全年样本242行，2025带上年12月重叠265行；22个重叠交易日价格/量一致。腾讯沪深300指数2024全年242行，可作为“实际观察交易日历”，不冒充官方未来日历。
- 中证官网成分XLS两次20秒超时；新浪公开沪深300成员API可访问，正在分页核对300唯一成员。只使用抓取时点成分，明确存活偏差。
- **官方成分关键更新**：获准沙盒外25秒读取中证官方XLS成功，301行含表头，300唯一证券，日期全为2026-11-09。与新浪节点有62只差异，因此最终不采用新浪节点作为股票池；正在切换中证2026-11-09官方成员，复用已下载相同证券原始行情。仍是晚于回测区间的单时点股票池，有存活/选择偏差。
- 已有9项隔离测试通过：研究虚拟份额/策略下一开盘、纸账户拒绝及sync隔离、缺口/停牌不执行、原文件hash、真实截止报告、分段冲突拒绝、幂等导入保护既有策略和running模拟会话。完整回归尚未执行。
- 首次全量回归：170 passed、2 failed，54.30秒。失败 `test_batch_deadline_counts_remaining_samples`（原媒体测试0.03秒预算在并行IO负载下先超时）、`test_cancellation_date_remains_attempted_bar_after_later_notification`（paper工作组并行开发中的取消日期）。本工作组未修改这些文件；日志 `.runtime/phase3-data-evidence/full-pytest-initial.log`，最终还会复核。
- 原新浪300只全数抓取成功，但仅作为初次来源比较保留，不正式导入。切换官方池后268只成功，32只在腾讯旧HTTP端点返回501（响应为腾讯WAF页面）；使用AKShare 1.20.37所记录的当前公开 `proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get` 端点的小样本成功，现以两并发补抓这32只。不会解验证码、登录或伪造数据。新响应可能回传请求起点以前最多640根，导入严格裁剪到请求范围，并检查分段重叠一致性。
- 定向旧流程回归41项通过（研究/导入/原回测/时钟/应用集成）；外部paper取消日期复测已通过。原媒体30ms期限用例单独仍失败，paper工作组也确认独立初始化耗时超过该测试预算，需协调处理。

目标请求区间 `[2024-01-01, 2026-11-01)`。只保留真实返回的数据，不补未来日期或缺口。最终真实范围 **2024-01-02至2026-10-30**，官方股票池日期 **2026-11-09**，**300只全部取得，203,572条研究日线**。逐股原始未复权和前复权响应均保存；1209个manifest所引用文件通过SHA256校验。

正式8765服务不重启，不调用 store.init（会暂停会话）。下载落 data/history，最终协调停服备份/迁移/重启后导入。测试使用隔离DATA_DIR，不修改正式策略/订单。

## 最终数据与完整性

唯一最终包：`data/history/hs300-20240101-20261101/`。

- `manifest.json`：请求URL/参数、逐文件抓取UTC时间、SHA256、官方池元数据、成功/失败证券；最后抓取UTC为2026-11-10T09:51:57.912303+00:00。
- `universe/csi-000300.xls`：中证指数官方原表，300唯一股票；`universe/members.json`：代码/中文名标准化元数据。表内日期2026-11-09晚于回测截止，明确有存活/选择偏差，不声称历史每日成分。
- `bars/`：旧腾讯公开端点原响应，`bars-current/`：当前公开端点补抓的32只证券，均保存未复权和qfq。新端点只用于缺失证券，并对该证券完整重取两个片段，不混用半个新旧复权序列。
- `calendar/`：沪深300指数实际日线，共683个观察交易日。不是官方未来交易日历。
- `integrity-report.json`：300只逐股日期、行数、全部缺失日期；`dataset-summary.json`：可直接提供UI的元数据。
- 300只全部返回到2026-10-30，失败股票0、尾部缺口0。271只覆盖683个观察交易日；29只存在缺失，共1328个“股票×交易日”，其中内部缺失248、头部缺失1080。保持 `coverage.status=partial`，不能声称300条完整连续序列。
- 头部缺失4只：000657.SZ从2024-01-10（677行）、001280.SZ从2025-12-03（219行）、001391.SZ从2024-12-30（443行）、600930.SH从2025-07-16（313行）。没有凭空补上市前或停牌价格，也没有仅凭缺口推断其原因；未单独取得每个缺口的官方停牌/上市原因文件。
- `*-sina-initial.json`、`*-csi-first.json`、probe/及failure日志仅保留来源尝试历史，不是最终导入入口。新浪节点相比官方表落后62只，未正式采用。

数据集ID：`history-47b06d31f484158407a147cf`。

Manifest SHA256：`47b06d31f484158407a147cfb410dfba75332f48c16e422aedf5e00db3c89ee0`。

标准化研究rows SHA256：`e03b977fa52cae3b1dcf60ea993b2d7c6f58c431edcdc75204c310b7184626dc`。

## 实现与研究含义

- `app/trading/history.py` 验证hash、日期、OHLC、量、原始/复权日历、分段重叠、官方池代码，再构建单个不可变dataset。文件hash不匹配立即拒绝；证券序列不一致会计入失败，不静默拼接。
- `app/trading/research.py` 独立研究账户执行器，复用既有 `engine.signal`，因此所选策略/启用项/权重/冲突/阈值/均线/止损仍实际生效。信号收盘生成，下一根开盘调仓。虚拟份额可分割，精度8位；价格保留供应商复权精度，研究现金按分计价。
- 研究资金/股数不映射真实股票账户。分红送转只反映于供应商复权序列，无额外分红现金或股数；不是精确股息再投资现金流。阈值须按该复权尺度配置。复权含事后信息，不能宣称逐时点无未来信息；无官方限价/盘口/整手/真实公司行为现金流撮合。
- 停牌/零量和缺失交易日之后的首根不执行旧调仓意图，不补造行情。均线按可用bar根数计算，缺口不补入指标。
- `models.py/service.py/router.py/datasets.py` 增量支持研究类型、全沪深代码回测、数据快照/单位/能力说明；原CSV范围和SessionInput股票范围仍严格。研究数据创建模拟会话或sync切入原会话均400；不更改原engine/store。
- `scripts/fetch_hs300_history.py` 公开接口批量、有限重试/并发、断点缓存、两年片段与重叠核对、离线验证/显式导入。`--retry-failed` 使用AKShare当前记录的公开端点，不解验证码、不注册账号。公开可访问不代表获得商业数据授权。
- 可选依赖 `requirements-history.txt`：BaoStock用于首选连通测试，xlrd只用于读取官方XLS；最终离线导入与运行回测无需这些可选包。未修改原requirements。

## 正式导入交接（协调执行，无需用户上传CSV）

本工作组**没有写正式 trading.sqlite3，也没有重启8765**。目前运行的旧服务未加载研究执行器，不宜提前把新类型暴露给旧进程。协调按既定流程停止旧服务、备份正式data，再运行以下命令，随后启动新版服务：

```powershell
.venv/Scripts/python.exe scripts/fetch_hs300_history.py --output data/history/hs300-20240101-20261101 --validate-only --import-data-dir data
```

该命令完全离线；目标DATA_DIR若非默认请替换 `data`。只在SQLite事务里插入一个kind=dataset记录，不迁移策略/订单，不调用会暂停paper会话的store.init，不覆盖同ID内容。重复运行返回同一dataset_id，不新增副本。导入后 `GET /api/trading/datasets` 可看到300个symbol_metadata，POST /backtests可运行。前端契约已由界面工作组消费。

重新验证（隔离数据，不动正式库）：

```powershell
.venv/Scripts/python.exe scripts/fetch_hs300_history.py --output data/history/hs300-20240101-20261101 --validate-only
.venv/Scripts/python.exe scripts/fetch_hs300_verify.py
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase3-data-check-unique -p no:cacheprovider
```

首次重抓或新目录：安装requirements-history.txt后运行fetch脚本；默认走官方成员表及旧腾讯端点。若旧端点部分501，保留结果再加 `--retry-failed --workers 2`。官方文件已通过批准的沙盒外读取保存；只重用当前包无需再联网。

## 最终验证

- 新增10项history/research测试：先观测缺能力失败，再实现通过；涵盖下一开盘/虚拟份额/现金复算、策略执行、纸账户和sync隔离、缺口和停牌、hash拒绝、分段冲突、官方池日期/唯一性、导入幂等且既有running模拟状态及策略不变。
- 研究与原回测/时钟/应用集成41项通过，5.64秒。
- 最新全量 **178 passed，104条上游Backtrader弃用警告，26.08秒，退出0**，`.runtime/phase3-data-evidence/full-pytest-final.log`。初次其他工作区失败记录保留在下方；后续并行工作修复后全量通过，本工作组没有越权改媒体/paper文件。
- `scripts/fetch_hs300_verify.py` 真实完整包两次导入隔离库，仅1个dataset；真实FastAPI请求创建明确测试MA5/20、80%仓位策略，分别运行600000.SH、300750.SZ、688981.SH、302132.SZ并各重复一次，成交序列/metrics一致，所有signal_date严格早于成交日；资金非负、真实净值/费用产生。研究数据进入paper返回400，纸账户仍空。
- 上述真实API检查用时39.742秒，独立DATA_DIR `.runtime/hs300-real-api-a4dfdd9c07`，证据 `.runtime/phase3-data-evidence/real-api-verification.json`。这些是验证参数，不是修改正式用户策略，也不是收益推荐。
- 全缓存再次运行补抓命令后manifest SHA256不变；离线验证仍300只、203572行、0失败、0尾部缺口。期间发现缓存元数据合并用旧members格式hash覆盖新格式的问题，由真实hash校验阻止导入；修正合并优先级后完成上述重复验证。
- 基础自查覆盖需求、主流程和明显回归；未做对抗审计。剩余阶段工作为协调正式导入、前端/独立基本验收和最终接受。

## 来源

- BaoStock官方包及匿名登录范例：https://pypi.org/project/baostock/
- AKShare官方行情接口说明：https://akshare.akfamily.xyz/data/stock/stock_quote.html （stock_zh_a_hist_tx）；实际检查PyPI 1.20.37包源代码中的当前腾讯端点及参数。
- AKShare官方成分接口说明：https://akshare.akfamily.xyz/data/index/index.html （index_stock_cons_csindex / index_stock_cons_sina）。
- 中证官方原始文件：https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000300cons.xls
