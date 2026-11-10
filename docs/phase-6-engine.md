# Phase 6 — 指标、条件 DSL 与区间回测

工作目录 `C:/Users/Admin/Desktop/quant`；本工作组拥有 `app/trading/`，不操作正式数据或服务。协调要求直接实施；不新建线程或子代理。状态：22:30前实现与基本自检完成，交协调组织独立基本验收；以下为已实现接入契约。

## HTTP 接入契约（前端与 AI 共用）

- `GET /api/trading/capabilities` 保留旧字段，`rule_types` 增加 `conditional`，新增 `indicators`（名称、label、参数默认值、范围、说明）、`condition_operators`、`rule_schema`（完整 JSON Schema）、`execution`、`unsupported_conditions`。
- `GET /api/trading/indicators` 返回 `{frequency: "daily", indicators: [...], condition_operators: [...], rule_schema: {...}}`；注册表名称区分大小写。
- `POST /api/trading/backtests` 增加可选 `start_date`、`end_date`，严格 `YYYY-MM-DD` 字符串；省略表示所选标的可用首/末日；倒序、日期无效为 422，区间没有行情为 400。
- 日期区间仅用于回测；本地/外部模拟会话若提交日期区间会返回400，避免静默忽略。模拟盘仍使用同一套指标与条件执行器。
- 回测返回保留原字段，新增 `requested_start_date`、`requested_end_date`、`actual_start_date`、`actual_end_date`、`initial_equity`、`final_equity`、`pnl`、`warmup_bars`。`metrics` 同步增加 initial_equity/final_equity/pnl。
- 起日前的数据只供指标预热，不产生交易、策略持仓状态或区间盈亏。区间首日收盘首次产生策略信号，下一日开盘执行；结束日收盘按市值计算，不强制平仓、不虚构后一日成交。

## 新规则格式

```json
{
  "type": "conditional",
  "target_pct": 50,
  "buy": {
    "op": "and",
    "conditions": [
      {"op": "cross_above", "left": {"indicator": "MACD_DIF", "params": {"fast": 12, "slow": 26, "signal": 9}}, "right": {"indicator": "MACD_DEA", "params": {"fast": 12, "slow": 26, "signal": 9}}},
      {"op": "gt", "left": {"indicator": "RSI", "params": {"period": 14}}, "right": {"value": 50}}
    ]
  },
  "sell": {"op": "lt", "left": {"indicator": "CLOSE"}, "right": {"indicator": "MA", "params": {"period": 20}}}
}
```

- 比较操作：`gt/gte/lt/lte/eq/ne/cross_above/cross_below`；逻辑：`and/or`，使用 `conditions` 数组。叶子左右操作数为 `{value: number}` 或 `{indicator: NAME, params: {...}, offset: 0}`，offset 为过去日线根数，0 是当前收盘，禁止负数/未来引用。
- `buy`、`sell` 都必填；持仓时 sell 优先于 buy；空仓时仅 buy 可入场；均不满足维持目标。可选 `stop_loss_pct` 保留原语义：相对入场信号收盘价，收盘判断、下一开盘执行。不是成交成本止损。
- 交叉定义：昨日左<=右且今日左>右为上穿；昨日左>=右且今日左<右为下穿。任一所需指标未预热/不可用时条件为未知，AND/OR 按三值逻辑，只有确定为真才触发。
- 周期按交易日线根数；不跨标的计算；MA/EMA/RSI 等 period 1..250（实际范围见注册表），offset 0..250。每棵条件树最多 64 节点、8 层。
- 指标：OPEN/HIGH/LOW/CLOSE/VOLUME/PREV_CLOSE、MA/EMA、MACD_DIF/MACD_DEA/MACD_HIST、KDJ_K/KDJ_D/KDJ_J、BOLL_MID/BOLL_UPPER/BOLL_LOWER、RSI、ATR、CCI、WR、OBV、VOLUME_RATIO、CHANGE_PCT、GAP_PCT、AMPLITUDE_PCT、LIMIT_UP/LIMIT_DOWN、IS_LIMIT_UP/IS_LIMIT_DOWN、LIMIT_UP_STREAK、FIRST_LIMIT_UP。
- KDJ 采用 RSV 后递归平滑，K/D 初值50，J=3K−2D；MACD HIST=2×(DIF−DEA)；BOLL 总体标准差；WR 范围 -100..0；VOLUME_RATIO=当日量/此前N根均量（不含当日），与盘口量比不同。完整公式、预热说明由注册表提供。
- 指标实际注册32项（一个多输出指标的各输出分别注册）；MA/EMA 支持 `field: open|high|low|close|volume`，默认 close。RSI 单边上涨为100，平盘为50；KDJ零振幅RSV为50；WR零振幅为-50；CCI零偏差为0；成交均量为0时量比未知。
- 已确认且没有待解决问题的 conditional 规则可承载原草案 `filter` 类型；旧 ma/threshold 仍拒绝遗漏过滤条件。原草案 `other` 仍阻止执行，用户确认与证据映射流程不放宽。

## 一进二的可执行边界

`FIRST_LIMIT_UP == 1` 可在首板日收盘产生次日开盘入场意图；`FIRST_LIMIT_UP(offset=1) == 1 AND CHANGE_PCT > 0` 是首板次日收盘确认，实际第三日开盘买入。两者不同，不能把后者声称为次日盘中打板。

涨停以导入的真实 `limit_up` 价格比较，不能一律用涨幅>=9.9%替代；板数按连续收盘封板计算。数据起点之前是否已连板未知时，不能伪称首板。复权研究数据没有可信每日涨停价，含涨跌停/板数规则拒绝运行。

竞价成交额、竞价强弱、开盘后突破、封板时间、炸板/回封、排队成交、题材/板块地位、流通市值/换手率筛选等若缺对应数据或执行模型，必须返回明确待确认问题；不能改成 MA 规则并称为已映射。

## 官方来源

- TA-Lib 官方指标清单：https://ta-lib.org/functions/ ，https://ta-lib.github.io/function.html （2026-11-10 查询；用于标准指标名称，项目具体初始化与输出变体以注册表为准）。
- TA-Lib KDJ 公式及初始化差异：https://ta-lib.org/functions/kdj.html 。该官方文档说明递归初始化存在平台差异；本项目明确选初值50，而非声称与TA-Lib默认初始化一致。
- TA-Lib MACD：https://ta-lib.org/functions/macd.html 。官方默认Hist=DIF−Signal；本项目明确采用中文行情常见双倍柱定义，API 名称为 MACD_HIST。
- TA-Lib CCI：https://ta-lib.org/functions/cci.html ，以及 https://ta-lib.github.io/ta-doc/indicator/BBANDS.htm 、https://ta-lib.github.io/ta-doc/indicator/RSI.htm 。
- 上交所《交易规则（2026年修订）》：https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml （2026-11-10 查询；本系统消费每根实际涨跌停价格，不通过旧固定比例猜测）。

## 验证记录

已实现主要代码，扩展边界测试与全量回归完成。

当前新增21项通过；公式、未知值/零分母、全部指标的前缀不变性与缓存JSON恢复、区间含未平仓市值、研究复权数据限价拒绝、来源过滤条件兼容均覆盖。研究数据缺 `prev_close` 时可从无缺口的前一根收盘推导；首根或明确缺口后保持未知。

22:28 全项目 `.venv/Scripts/python.exe -m pytest tests -q`：**431 passed**，126条Backtrader既有弃用提示；包含并行工作组当时的AI条件映射测试。随后基本复核新增ATR缺口测试：缺失交易日后的昨收不可用时，ATR返回未知并重新预热，避免把跨缺口的旧收盘冒称昨收。

**最终回归（22:30前）：`.venv/Scripts/python.exe -m pytest tests -q` → 432 passed，126条Backtrader datetime.utcnow弃用提示，43.79秒；退出码0。** 新增引擎测试22项包含在内，主要源码本轮之后未再修改。本组实施范围无未关闭缺陷；完整视频的盘中数据/执行缺项为已声明能力边界，不冒称完成映射。

全目录 `.venv/Scripts/python.exe -m pytest -q` 意外递归收集正在生成的 `output/StrategyWorkbench-0.6.0-windows-x64/runtime/python/Lib/site-packages`，出现7个收集错误（5个colorama导入路径冲突、numpy缺hypothesis、onnxruntime缺psutil）；这是便携包第三方测试收集，并非项目用例失败。后续明确执行 `.venv/Scripts/python.exe -m pytest tests -q`，不删除或修改打包目录。

- 初始新增12项通过；交易/研究/外部模拟/AI后端与新增测试相关回归91项通过（Backtrader既有104条datetime.utcnow弃用提示）。
- 新增首板规则夹具：前一日非涨停→首板日→次日正常开盘；实际回测于次日买入，本地模拟回放 fills/signals 与回测一致。额外验证BackBroker消费同一条件信号；撮合金额差异沿用原两个撮合器定义。
- 区间验证：起日前阈值信号不泄入区间；MA可以用起日前价格预热；区间第一天发信号、第二天开盘成交，按区间末收盘市值计算盈亏。

### 实际已导入一进二资料（仅只读核对）

2026-11-10 使用 SQLite `mode=ro` 查询 `data/workspace.sqlite3`。资料《一进二 #龙头主升战法 #打板》，282段；查询时 `strategies` 表为空。没有修改转写、生成真实草案、调用用户模型或创建正式交易资源。本文仅记录段号与能力差距，原文保留在用户本机资料库。

以下是原ASR段落的语义核对（存在错词，不能把分析概括当成已确认校正文）：

| 原文位置 | 能力差距 |
|---|---|
| s58–s72，121.4–148.6秒：同板块前后排、上板强度、排队资金/封单相关表述 | 需要跨标的题材/板块与盘口数据，单标的OHLCV不能表达完整筛选 |
| s110–s122，214.4–237.0秒：竞价信号、分时放量、上板瞬间大单 | 当前缺集合竞价、分钟/逐笔和盘口数据 |
| s128，247.0–249.2秒：回踩均线后再封板 | 涉及盘中时序，不应替换成日线MA买入 |
| s137–s138，263.4–266.4秒：先买底仓、封板瞬间加仓 | 条件触发的分批加仓与封板时刻撮合未支持 |
| s168–s179，307.8–323.6秒：开盘状态、炸板后5分钟内回封/失败退出 | 日线不能验证5分钟、炸板与回封时序 |
| s244–s248，414.1–424.1秒：总资金分4份，每天1至2只，单票不超50% | 单标的目标仓位可表示50%上限；跨股票池、每日数量限制及组合资金分配未完整支持 |

结论：真实视频需要明确补充数据与执行模型，当前不能宣称已完整映射/可直接运行。新增测试的日线首板规则是独立的、完整定义并确认的合成验证夹具，绝非视频原策略替身。

## 实现交接

- 新增 `app/trading/indicators.py`：32项注册表、统一参数验证、只追加的可序列化指标缓存；无新运行依赖。
- 新增 `app/trading/conditions.py`：递归schema、三值逻辑、比较与交叉、历史offset、原始限价能力检查。
- 修改 `models.py`：conditional规则、可选日期及顺序验证；旧ma/threshold契约保留。
- 修改 `engine.py`：统一条件信号；研究回测、本地模拟、BackBroker均通过现有共享函数消费同一语义。
- 修改 `service.py`：区间预热、结果盈亏、空区间拒绝、复权数据板数规则拒绝。
- 修改 `router.py`：能力与指标目录API；修改 `paper_service.py`：显式拒绝模拟会话日期参数。
- 精确修改 `portfolios.py` 的支持类型判断：conditional可带已确认的日线filter，保留Phase5候选与其它就绪检查。
- 新增 `tests/test_phase6_engine.py`：22项测试；没有修改原有测试期望来掩盖行为变化。
- 单机性能烟测：3000根合成日线、MACD条件，约1.21秒完成，3000个信号。只是实现性能检查，不代表交易表现。

不需要数据迁移。所有新增交易资源/模型响应验证均在临时测试库；本组没有操作Git、重启正式服务、调用真实供应商或修改正式资料与行情。
