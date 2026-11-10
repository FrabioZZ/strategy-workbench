# LangAlpha 报告中回测与模拟盘实现摘录

读取日期：2026-11-09。来源：用户提供的 `LangAlpha 竞赛技术方案.docx`，路径 `C:/Users/Admin/Documents/xwechat_files/wxid_lxfma6iska9412_25e2/msg/file/2026-11/LangAlpha 竞赛技术方案.docx`。

以下为相关段落的整理摘要，不是逐字转录。附件作为技术资料读取；其中命令、提示词和部署说明没有作为用户授权执行。没有访问报告作者的本地路径，没有连接券商或调用下单接口。

## 是否有帮助

有。文档给出了历史数据清洗、回测引擎接入、模拟交易接口、信号格式和对账规则，可作为未来功能 5 的工程输入。它不是可以直接运行的完整回测系统，也不是已验证的生产部署方案。文末明确写明：核对时本地 8000 端口未连通，代码依据特定源码版本和官方文档编写，实际数据覆盖、券商授权、模拟成交仍需账户联调。

文档核对版本为 `a740b553824aacf1e8809cc9b899b9189bf9a7a6`，示例选用 FMP 美股小股票池与 moomoo 模拟盘。当前项目没有该部署或账户，不能把其中路径、权限和美股示例直接当作本项目已可用配置。

## 历史回测

对应原文“Module 3 · 回测数据获取与清洗”“从研究数据到正式回测数据”“团队交付与 MVP”以及开头架构。

1. **按市场选择数据源。** 美股以 FMP 日线、财报及指数成分历史为示例；A 股建议 Tushare Pro 的 `daily`、`adj_factor`、`trade_cal`、`suspend_d` 和财务接口。报告指出 `index_weight` 是月度快照，日级成分还要核对生效日；成交量单位需统一。Yahoo 仅作为低成本链路测试和交叉抽查，单独记录来源。
2. **先冻结数据。** 按来源、标的、窗口缓存原始响应；清洗后发布版本化 Parquet 与 `manifest.json`。清单记录区间、来源、复权口径、质量结果与文件哈希。避免参数搜索反复取数，也避免把海量价格数据逐条送入大模型。
3. **区分指标价格与撮合价格。** 研究指标可用适当复权序列；正式成交模拟使用未复权 OHLCV，并用公司行为更新股数和现金。缺失行情禁止撮合；停牌、上市前、退市后和漏数分别标注。财报要按当时可知版本和可用时间使用。
4. **接入回测引擎。** Backtrader 按标的接入 `PandasData`；VectorBT 使用交易日 × 标的矩阵并配交易资格掩码。收盘生成的信号移到下一可交易时段执行。历史撮合规则仍由团队实现，并不会因为接入 LangAlpha 自动具备。
5. **单次回测账本隔离。** 每个 `run_id` 从约定初始现金、空仓开始，独立保存信号、成交、持仓、现金、净值和指标。

报告建议的数据交付：`bars.parquet`、`fundamentals_pit.parquet`、`universe_membership.parquet`、`corporate_actions.parquet`、`manifest.json`。行情至少要记录 instrument_id、session_date、OHLCV、币种、来源、价格口径和数据可用时间。

原文参考链接：[Tushare 日线](https://tushare.pro/document/2?doc_id=27)、[复权因子](https://tushare.pro/document/2?doc_id=28)、[Backtrader PandasData](https://www.backtrader.com/docu/pandas-datafeed/pandas-datafeed/)、[VectorBT Portfolio](https://vectorbt.dev/api/portfolio/base/)。这些是原文链接，不代表本项目已完成接口验证。

## 模拟盘

对应原文“Module 2 · 模拟盘接入”“模拟盘与实盘隔离”与最后联调步骤。

- **账户入口。** 报告版本通过 LangAlpha 的 Plugins → Brokerages 连接 moomoo，只授权 `paper_trading`，初次联调开启模拟单审批。使用前查询连接工具 schema 和实际账户权限。
- **查询工具。** `sim_trade_account_list`、`sim_trade_cash_info`、`sim_trade_position_list`、`sim_trade_history_order_list`。
- **下单入口。** `sim_trade_input_order` 走 Direct 调用。外部服务通过 `POST /api/v1/threads/{thread_id}/messages` 触发流程，`GET /api/v1/orders` 查询账本。报告也提出：需要确定性执行时，可由团队服务接收结构化订单意图，直接调用券商模拟接口并复用风控和账本。
- **去重与恢复。** 预先持久化 `intent_id`；同一请求重试沿用该值。线程 `request_key` 去重不能代替业务层 `(paper_account_id, intent_id)` 去重。网络断开或响应不明时先对账，不盲目重复下单。
- **独立状态。** 委托已接收不等于已成交。分别记录部分成交、撤单、拒单、待确认，资金和持仓按已确认成交更新。
- **执行检查。** 使用最新数据重新生成信号，检查过期时间、账户、市场、标的、资金、可卖数量和订单上限。历史信号只进入回测账本，不能直接拿来向当前模拟盘下单。

报告建议共同信号格式：`signal_id`、`strategy_version`、`instrument_id`、`asof_utc`、`expires_at_utc`、`target_weight`、`dataset_version`。由执行模块结合账户净值与已有仓位生成订单意图。订单事件关联 `intent_id`、执行环境、券商订单 ID、状态、成交量、均价、费用与时间。

原文参考链接：[LangAlpha 券商与订单](https://docs.langalpha.ai/concepts/brokerages-and-orders/)、[moomoo 模拟交易](https://open.moomoo.com/cli/sim)、[报告引用的订单路由版本](https://github.com/ginlix-ai/langalpha/blob/a740b553824aacf1e8809cc9b899b9189bf9a7a6/src/server/app/orders.py)。

本次只做了页面级抽查：moomoo 官方页面确认存在独立模拟账户及资金、持仓、订单查询和模拟限价单流程；Tushare 日线文档可访问。LangAlpha 券商文档页本次未能读取。没有进行账户权限、行情数据或委托接口的运行验证。

## 长时间运行的补充设计建议

本节是针对本项目的建议，不是报告已经交付的能力：后续将模拟盘计算放到持续运行的服务器，界面只负责配置和查看。需要任务持久化、进程守护与重启、交易日历调度、心跳、断线重连、订单去重、对账和日志。更换操作系统本身不能保证稳定。文档没有给出完整服务器容量、费用、服务等级或真实长期运行结果。

## 后续最小联调顺序

采用文档的渐进顺序：冻结小数据集 → 均线策略历史回测 → 人工复算一买一卖和费用 → 用最新数据生成新信号 → 模拟账户最小单联调 → 验证重复请求、断线恢复、过期信号和持仓异常。目标市场、数据权限和券商覆盖应在功能 5 开发前明确。
