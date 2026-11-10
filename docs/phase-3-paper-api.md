# Phase 3 外部模拟 API（已实现稳定契约 v1）

前缀 `/api/trading/external-paper`。独立 kind=`paper_external`，JSON 账本置于 trading.sqlite3，与原 kind=`paper` 隔离。错误继承 400/404/409/422；缺可选包返回503；所有内部 `_` 字段不对外暴露。

挂载（协调负责）：`from app.trading.paper_service import PaperService`；创建 `external_paper = PaperService(trading_store, store)`；在 lifespan 的 trading_store.init() 后 `external_paper.recover()`；`from app.trading.paper_router import router as external_paper_router`，`app.include_router(external_paper_router(external_paper))`。

无需后台 worker。支持暂停单步及一次完整运行；执行在请求内完成，事务提交后原子保存。页面明确显示历史回放，不提供实时/增量模式。

- `GET /capabilities` → engine/name/version/installed/license/account_required:false/live_supported:false/modes:["replay"]/limitations。
- `POST /sessions`（201）：与原 RunInput 相同，加 `name` 与 `mode:"replay"`（默认）。必须 dataset_id。创建 paused，无成交。启动时冻结组合版本、数据hash、引擎版本及参数。
- `GET /sessions` → Session[]；`GET /sessions/{id}` → Session。
- `POST /sessions/{id}/step` `{request_id}`：paused 单步一根。
- `POST /sessions/{id}/run` `{request_id}`：paused 从当前游标完整运行到末尾并置 completed。
- `POST /sessions/{id}/pause` 无body：幂等暂停（不删除已完成账本）。

step/run 都再次检查原组合仍就绪且版本相同；既有快照始终不改写。同 request_id 同 action 幂等，不同action 409。已完成会话重复run无新增成交。恢复只对非completed会话置paused。

Session：`id,kind,name,mode,status,created_at,updated_at,engine:{name,version,license},portfolio_id,portfolio_revision,portfolio_snapshot,dataset_id,dataset_hash,symbol,initial_cash,costs,is_demo,warnings,cursor,consumed_bars,total_bars,cash,positions,signals,orders,fills,equity,metrics,message`。订单 status=`submitted|accepted|filled|rejected|cancelled`，含 `id,signal_date,date,symbol,side,quantity,price,fee,reason,engine_status`。fills为实际引擎已完成订单，metrics含total_return_pct/max_drawdown_pct/fees/trade_count。

额外 `dataset_snapshot` 为不含rows的数据元信息（来源、价格口径、日期、hash等）。engine同时返回 `expected_version`、`installed`，依赖版本不匹配也视为不可用。订单id在同一会话内稳定，以symbol/信号日/方向组成；不要跨会话将它当全局成交ID。待成交订单date/price为null。持仓quantity/available_quantity为实际模拟股数，average_cost不含交易费用。

采用收盘计算固定股数（100股整手），下一根开盘市价撮合，保留 BackBroker 资金不足拒单；不使用未来开盘价预先决定股数。费用为工作台成本参数（自定义 CommissionInfo），滑点由BackBroker处理。停牌、零量、开盘触及涨跌停保守不成交，未成交订单在该根收盘撤销，不跨日排队。末根信号可存在submitted订单，不能虚构额外行情来完成它。

每根都会依当前收盘净值重新平衡目标仓位，可能出现100股小幅调仓，不承诺与旧引擎成交数量一致。滑点价格超出当日高低区间时不成交，不将价格截断伪造成交。服务端模式固定replay；不接受incremental、替换数据集或实时同步参数。`pause`只保留暂停状态；完整run为一次原子请求，不提供运行中途撤回语义。

前端 `paper-external.js` 自行追加到 `#workspace-paper`，独立类名前缀 `pex-`；协调只需注册 CSS/JS。现有 DOM 不改写。普通组合和数据经原 `/api/trading/portfolios`、`/datasets` 获取。
