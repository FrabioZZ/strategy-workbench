# Phase 11 · AI 补全执行规则

共享目录 `C:/Users/Admin/Desktop/quant`，分支 `main`。协调聊天 `01a1ca9e-da28-7a61-9ddf-3a293c56455d`，AI 实施聊天 `01a1caa1-9bd5-7a22-a572-de62321f4eb1`。

## 演示对接合同

- 建议资料四行。第一行 `600000.SH，日线。`，第二行 `收盘价站上5日均线且放量时买入。`，第三行 `收盘价跌破5日均线时全部卖出。`，第四行 `目标仓位20%。`。抽取草案的 asset 为 `600000.SH`、timeframe 为 `日线`，保留 buy/sell/position 三条及逐字引文。段 ID 按导入实际生成值。校对替身返回 `{"changes":[],"questions":[]}`。
- `POST /api/ai/strategies/{source_id}/mapping/complete` 请求体 `{"source_revision":1}`，采用正常资料提取产出的实际修订。复用 `app.ai.client.complete(settings,messages,schema)`。模型最后一条消息为 JSON，含 `untrusted_strategy`、`untrusted_transcript`、`clarifications`。后者各项有 `id`、`field`、`quote`、`segment_id`、候选 `options`（含 `id`、`label`、`values`），以及适用的 `custom_fields`。
- 模型回复 JSON `{"decisions":[{"question_id":"<从输入读取>","option_id":"cross_above","reason":"把站上解释为由下向上穿越，避免持续在均线上方时重复触发。"},{"question_id":"<从输入读取>","option_id":"previous_20_x1_5","reason":"原文没有给量比阈值，采用此前20日均量的1.5倍作为演示假设。"}]}`。按字段 `ma_stand_above`、`volume_ratio` 读取 ID，勿写死。`custom` 须提交 `values`，其余选项省略。模型可省略无法判断的问题，结果继续待人工确认。原文无明确证据时，结果标示 `basis: assumption`。
- 行情需至少 20 根日线预热，在同一根上使收盘价由均线下方或等于均线转为上方，且成交量大于此前 20 根均量的 1.5 倍。买入信号次日开盘执行。`跌破` 沿用现有下穿语义，从上一根收盘价在均线上或等于均线转为本根低于均线时触发，次日开盘执行。
- 响应沿用映射字段。就绪时增加 `resolution_method: ai`、`mapping_version`、可人工改选的 `clarifications`，以及含 `basis`、`reason`、`label` 的 `decisions`。修改当前 AI 方案用原人工映射接口并附所见 `mapping_version`。组合项保存 `mapping_version`，照常填写映射说明并由用户明确确认。

## 实施顺序

1. 用隔离数据库与模型替身固化端到端合同及失败路径，模型只选择候选或提交合法自定义值。
2. 扩展映射路由、版本比较和组合快照，使用现有术语、全文覆盖与规则校验编译最终规则。
3. 资料页和组合映射区域接入主动补全、人工改选和最终确认，运行 Python 与浏览器回归。

## 实施结果

- 资料页「让 AI 补全并生成执行规则」进入组合并自动提交补全。组合内可重试、查看规则和参数证据、调整各项口径。应用新映射后需重新勾选确认并保存。现有「生成执行规则」和无请求体映射保留，日线口径仍可人工选择。
- 模型只返回术语问题 ID、已有选项或合法自定义数值及简短理由。术语库替换原句中的已注册术语，其他条件留给原有全文覆盖和条件树校验。原文缺交易意图、例外不受支持、校对存疑或条件冲突时保留待确认状态。原文足以编译完整规则时直接用本地规则验证并返回 `resolution_method: source`。
- `basis: evidence` 需要另一条可逐字核验且完整证明相同买入或卖出条件的原文，响应携带 `support` 引文。其余补全展示为 `basis: assumption`，包括演示的两项选择。明确的标的、周期、仓位、买卖和止损等字段以参数证据呈现。
- 存储核验原文修订和最新草案。先写入的就绪结果优先。人工改选通过 `mapping_version` 比对当前映射，成功后生成新版本并以 `resolution_method: manual` 返回。相同改选重试复用结果。此前保存的组合需要重新载入并确认最新映射，已记录的执行快照保留采用时的规则、证据和决议。
- 普通回测、行情工作台及外部历史回放的创建入口核验指定股票。版本化映射也核验明确的沪市、深市或主板范围。执行读取已保存条件与快照。

## 验证记录

- 使用隔离库和模型替身，验证原文、规则树、假设和确切证据、无模型人工路径、原文在调用期间变更、并发人工先保存、版本替换和冻结回测。浏览器回归在 320px 检查资料页交接、待确认、重试、采用理由、人工改选失败后保留已验证结果，以及保存重开。
- `.venv/Scripts/python.exe -B -X utf8 -m pytest tests -q -p no:cacheprovider --basetemp=.test-tmp/p11-ai-final` 通过 548 项。126 条 Backtrader `utcnow()` 弃用提示来自已有依赖。
- `node --test --test-concurrency=1 tests/test_phase10_mapping_ui.cjs tests/test_phase11_mapping_ui.cjs tests/test_transcription_ui.cjs` 通过 4 项。实际隔离演示的独立浏览器验收见 [Phase 11 基本验收](phase-11-acceptance.md)。
