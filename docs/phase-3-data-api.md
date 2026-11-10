# Phase 3 历史研究数据 API（实现契约）

状态：实现和隔离真实API验证完成，正式导入由协调执行。最终数据范围见 phase-3-data.md。沿用 `/api/trading`。

## 数据选择与搜索

`GET /datasets` 保持数组及原字段，新增研究数据 `dataset_type: "research_adjusted"`、`price_basis: "forward_adjusted"`、`market:"CN_A"`、`allowed_modes:["backtest"]`。旧数据无 dataset_type 视为严格撮合，可用于原回测/回放。

研究数据仍以同一个 dataset_id 选择整个股票池，`symbols` 包含可运行代码；`symbol_metadata` 为 `[{symbol,name,start_date,end_date,row_count}]`，用于代码或中文名称搜索。单次运行仍为单标的。

新增元数据：`requested_start_date`、`requested_end_date_exclusive`、`expected_end_date`（实际返回的沪深300指数最后交易日）、`universe:{name,as_of_date,source,survivorship_bias:true,date_semantics}`、`coverage:{status,actual_start_date,actual_end_date,successful_symbols,failed_symbols,missing_tail_symbols,calendar_end_date}`、`provenance:{provider,fetched_at,manifest_hash}`。数据源提前截止时如实展示实际范围和缺口；不得把请求截止当实际截止。`warnings` 包括研究语义及来源限制。当前官方股票池表内日期为 **2026-11-09**，非历史每日成分。

`coverage.status` 为 `partial` 或 `complete_observed_calendar`，后者仅代表逐股日期覆盖已观察到的指数交易日历。`failed_symbols` 是 `{symbol,error}[]`，不是数量；`successful_symbols` 是数量。`symbols_with_gaps`、`observed_trading_days` 可用于概况。`symbol_metadata` 另有 `missing_day_count/internal_gap_count/missing_start/missing_tail`；IPO之前/停牌等缺失原因不凭价格猜测。

## 回测

复用 `POST /backtests`，请求字段不变，RunInput 接受沪深主板/创业板/科创板代码。具体可用性由数据集决定。研究数据运行响应新增 `execution_model:"adjusted_research"`、`price_basis:"forward_adjusted"`、`quantity_unit:"synthetic_unit"`、`dataset_snapshot`（不含rows的完整元数据）。旧严格撮合 `execution_model:"strict_daily"`。

研究模式沿用现有策略信号、权重和冲突规则：收盘信号、下一根开盘，使用复权价与可分割的虚拟份额；初始资金/现金/净值是研究账户的计价单位，quantity 不是实际股票股数。分红送转只经供应商复权序列反映，不再额外支付股息。费用/滑点仍是用户假设。研究订单不是可执行真实委托，无官方限价/盘口/整手成交保证；停牌和零量不调仓，缺失交易日不补价格、不跨缺口执行旧信号。价格阈值必须按该复权尺度配置。供应商事后修订和全样本复权存在未来信息局限。

`orders/fills/equity/metrics` 保持原结构，份额可能是小数。界面必须明确标识“复权研究回测”，显示数据实际范围及限制，quantity 显示“虚拟份额”，不要称实际成交股数。

## 模拟盘隔离

所有研究数据禁止用于 `POST /paper/sessions`，也禁止在旧增量会话 sync 时切换进来，返回400中文原因。模拟盘数据下拉应排除 `allowed_modes` 仅 backtest 的研究数据。不会因新增股票代码放宽旧CSV/严格撮合的股票范围。

## 预置导入

本阶段通过服务端脚本验证原始文件hash后一次性导入，前端不要求300次上传，也不新增抓取公网按钮。脚本只创建不可变dataset记录；不写策略/订单/模拟会话。正式导入命令已记入 phase-3-data.md。

最终包已就绪：`data/history/hs300-20240101-20261101`，dataset_id=`history-47b06d31f484158407a147cf`。300只、203572行、实际2024-01-02至2026-10-30，29只存在头部或内部缺失、尾部缺口0，status=`partial`。`--validate-only --import-data-dir data` 为离线幂等导入，完整命令及隔离API证据见phase-3-data.md。
