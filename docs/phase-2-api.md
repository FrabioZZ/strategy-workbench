# Phase 2 Trading API（稳定契约 v1）

所有路径前缀 `/api/trading`，JSON UTF-8；除明确说明外成功 200，创建 201。错误 `{ "detail": "中文原因" }`：400 业务输入错误，404 不存在，409 版本/就绪/状态冲突，422 schema 错误。列表均直接返回数组。时间戳 UTC ISO8601，交易日 YYYY-MM-DD，金额元，仓位/权重/费率以文中单位为准。数值必须有限。

## 能力与草案

`GET /capabilities` → `{market:"CN_A_MAIN",frequency:"daily",supported_symbols:"沪深主板普通股票（非ST、非上市初期），单标的运行",rule_types:["ma","threshold"],broker:{connected:false,label:"未接入券商，仅本地模拟撮合"},feeds:{csv:true,tushare_configured:false,tushare_verified:false},limitations:[string]}`。

`GET /strategies` → `[{id:string,document_id:string,title:string,revision:integer,stale:boolean,is_demo:boolean,strategy:object,transcript:array,created_at:string}]`。id 是持久化草案版本 ID；所有原规则、证据保留在 strategy 中。列表可为空，不制造策略。手工策略由组合项 `source_id:null` 表示。

## 组合

`GET /portfolios` → Portfolio[]；`GET /portfolios/{id}` → Portfolio。

`POST /portfolios` 请求以下对象；`PUT /portfolios/{id}` 同对象并必须加 `revision`（乐观锁）；保存可包含未确认/空组合，但不能运行。`DELETE /portfolios/{id}` → `{deleted:true}`，旧账本快照不删除。

```json
{"name":"我的组合","mode":"equal","conflict_policy":"block","items":[{"id":"item-1","name":"手工阈值","source_id":null,"enabled":true,"weight":100,"confirmed":true,"mapping_note":"已人工确认全部原规则均由当前映射表达","rules":{"type":"threshold","buy_below":10,"sell_above":12,"target_pct":100,"stop_loss_pct":null}}]}
```

mode=`equal|weighted`；conflict_policy=`block|weighted`；items 最多20个。item.id 为调用方生成的非空唯一字符串；name 非空；source_id 为草案 id 或 null；weight 0..100（百分比）；confirmed 为人工确认，须填写非空 mapping_note，必须用户确实确认后提交。rules 可为 null（阻止运行）。

规则联合类型：

- threshold：`{type:"threshold",buy_below:number>0,sell_above:number>buy_below,target_pct:number(0,100],stop_loss_pct:number(0,100)|null}`。低于等于买入线目标仓位 target_pct，高于等于卖出线目标0，区间保持该策略上次目标。
- ma：`{type:"ma",fast:integer[1,250],slow:integer[2,250]>fast,target_pct:number(0,100],stop_loss_pct:number(0,100)|null}`。快均线>慢均线目标 target_pct，否则0；预热期目标0并记录原因。止损以该策略最近从0变为非0时的信号收盘价为基准，收盘触发，下一根开盘执行；不是盘中止损，不以账户成交价混算各策略。

Portfolio 响应：上述对象 + `{id,revision:integer,created_at,updated_at,readiness:{ready:boolean,errors:[string],warnings:[string]},items:[上述item+{source_snapshot:object|null,effective_weight:number}]}`。source_snapshot 包含草案及转写证据冻结。PUT 对原 source_id 重新冻结；若该 id 过期仍阻止。启用策略有效权重按 equal 等分或 weighted 原值；weighted 合计必须100。禁用项effective_weight=0。

`GET /portfolios/{id}/readiness` → `{ready,errors,warnings}`；过期/重提取/转写变化重新校验；原草案有未解决问题、filter/other等未支持规则，或原文含止损而映射缺止损，均阻止运行。运行时冲突也可能阻止当日信号。`POST /portfolios/{id}/normalize` 请求 `{revision:integer}`，将启用项权重归一到100（全零则均分），返回新版Portfolio。不自动确认映射。

## 数据

`GET /datasets` → Dataset[]；`GET /datasets/{id}` → Dataset（含 rows）。`GET /datasets/template` → CSV 下载。

`POST /datasets/import` JSON `{name:string,source:string,csv_text:string,market:"CN_A_MAIN",price_basis:"raw",is_demo:false,ordinary_stock_confirmed:true,corporate_actions_confirmed_absent:true}` → Dataset。确认字段必须true；不支持ST、新股无涨跌幅限制期、其他板块、公司行为。CSV 必须有 `date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down`（正式数据使用官方每日限价，不能只根据昨收猜测）；可选 `suspended` 0/1。symbol 如600000.SH或000001.SZ，仅主板代码。日期严格升序（按date,symbol）、无重复，OHLC须合法，价格范围[0.01,10000000]，volume范围[0,1e12]，限价须合理。所有数据必须已完成日线，禁止未来/今日未收盘数据；最多10000行及约1.5MB CSV。成交价必须未复权。

`POST /datasets/demo` 无body → 演示 Dataset（600000.SH，固定历史价格，不依赖当前行情）。

Dataset: `{id,name,source,market,price_basis,is_demo,created_at,version:1,hash:string,start_date,end_date,symbols:[string],row_count:integer,warnings:[string]}`。详情额外 rows=`[{date,symbol,open,high,low,close,volume,prev_close,limit_up,limit_down,suspended:boolean}]`。数据不可变，增量导入产生新的dataset。

## 回测

`POST /backtests` → Run；请求 `{portfolio_id:string,portfolio_revision:integer,dataset_id:string,symbol:"600000.SH",initial_cash:100000,costs:{commission_bps:3,min_commission:5,sell_tax_bps:5,slippage_bps:0}}`。costs可省略，以上为默认可调整假设，不是自动税费规则。initial_cash [0.01,1e9]且最多两位小数；bps 0..100；最低费0..1000。

`GET /backtests` → Run[]；`GET /backtests/{id}` → Run。

Run: `{id,kind:"backtest",status:"completed",created_at,portfolio_id,portfolio_revision,portfolio_snapshot:Portfolio,dataset_id,dataset_hash,symbol,is_demo,initial_cash,costs,cash,positions:[{symbol,quantity,available_quantity,average_cost}],signals:[{date,target_pct:number|null,conflict:boolean,reasons:[string],components:[{item_id,name,target_pct,effective_weight,reason}]}],orders:[{id,signal_date,date,symbol,side:"buy|sell",quantity,price,status:"filled|rejected",reason,fee}],fills:[{order_id,signal_date,date,symbol,side,quantity,price,fee}],equity:[{date,cash,market_value,equity}],metrics:{total_return_pct,max_drawdown_pct,fees,trade_count},warnings:[string]}`。

运行单标的日线，首根只产生信号；信号用当日收盘及之前数据，下一根开盘撮合。按100股整手买入、只做多、T+1，停牌/无量/开盘触及限价/数据不足不成交且给原因；拒绝订单不跨日排队，下一日根据信号重新下单。开盘先卖后买（本期单标的）；滑点计入成交价。`conflict_policy=block` 且策略目标有分歧时 target_pct=null，当日不发新意图。费用、回撤实际计算。

## 模拟会话（本地独立账本）

`POST /paper/sessions` 请求回测同字段 + `{name:string,mode:"replay|incremental",feed:"csv|tushare",max_age_days:integer[1,10]}`，dataset_id 可为null（incremental；等待首批输入），feed默认csv，max_age_days默认4。→ Session。创建即paused。replay必须dataset，醒目标注历史回放；incremental禁止演示数据，首批历史数据仅预热，不撮合历史行。增量成交按该日北京时间09:30建模，必须严格晚于本次实际启动/恢复时刻和对应信号的实际观察时刻；两者作为内部时间戳随账本持久化，不能用最近完整日线日期替代。首次有效行情晚于start时，以实际观察时刻限制成交；盘前完成观察可在当天开盘撮合，盘中/盘后观察不能回填当天开盘。暂停/重启后恢复须重新观察有效行情，暂停期间的历史数据只用于更新指标与信号，不补成交。一次补入多根日线时，新生成信号也不得用于其实际观察之前的开盘。后续每次只处理大于游标的数据；超过max_age_days的行情/信号不成交；重复不产生新成交。日线完成采用北京时间18:00保守界限，max_age_days是自然日，不是精确交易日历。

`GET /paper/sessions` → Session[]；`GET /paper/sessions/{id}` → Session。

`POST /paper/sessions/{id}/start` 无body：从paused启动时再次检查源组合就绪及版本；冻结版本不匹配则409，返回Session。运行中再次start直接返回当前Session，不重置激活/观察时钟或已冻结组合。

`POST /paper/sessions/{id}/pause` 无body → Session，幂等。

`POST /paper/sessions/{id}/step` JSON `{request_id:string}` → Session；仅paused且replay，一次消费下一根，重复request_id不推进。必须每次有意单步生成新request_id。

`POST /paper/sessions/{id}/sync` JSON `{dataset_id:string|null,request_id:string}` → Session；仅running。replay一次下一根；incremental用指定数据或上次绑定数据（或配置的Tushare拉取）；重复request_id/数据无效消费幂等。CSV增量需先调用数据导入接口，可以包含全历史但已消费行不得修订；每次已消费日期数据不同则409。服务运行时每15秒轮询running会话：replay一次推进一根；incremental检查所绑定dataset/Tushare。CSV使用sync绑定新dataset。

Session: Run字段（kind="paper"，dataset_id/hash可null，status=`paused|running`）+ `{name,mode,feed,max_age_days,cursor:string|null,last_quote_at:string|null,heartbeat_at:string|null,feed_status:"waiting|fresh|stale|exhausted|error|paused",message:string,updated_at:string}`。即使feed_status等待/过期，status可为running；无假成交。进程重启全部paused、保留账本/游标，message解释需显式恢复。positions/signals/orders/fills/equity完整返回。旧会话冻结组合不会被编辑改变；版本变化后应建新会话。

Tushare仅服务端环境变量 `TUSHARE_TOKEN`（可选），默认不配置。适配器为盘后日线，必须同时取得daily和stk_limit官方限价；能力只报告配置存在，verified始终false直至外部真实联调另行完成。不会暴露token，不接券商或真实交易。

## 前端接入约定

所有按钮处理detail错误；list/get不修改数据。readiness只是静态就绪，数据/当日策略分歧错误见运行记录。所有演示数据、历史回放、未配置行情/券商必须持续标注。图表用equity序列，收益用metrics实际计算。草案source_id必须选GET /strategies中对应版本，禁止把任意草案自动填入ma默认映射。
