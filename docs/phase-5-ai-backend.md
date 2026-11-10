# Phase 5 — AI 后端工作记录

日期：2026-11-10。工作目录 C:/Users/Admin/Desktop/quant；非 Git，branch/worktree 不适用。本工作组只改设计授权的后端文件，不启动正式服务、不接触正式数据或凭据。

## 选用方案与契约

- 使用 `app/ai` 管理本机设置、HTTP 客户端、校正和映射。设置独立存于 data_dir/ai-config.json，Key 为 Windows 当前用户 DPAPI 密文；非 Windows 保存 Key 明确失败。配置删除保留无凭据的禁用标志，防止旧环境变量再次生效。配置接口检查实际请求来源为回环地址；不信任转发头。
- 原 `/extract` 队列入口不变。真实 Extractor 先校正再摘录；已有只实现 extract 的测试替身保持兼容。任务开始时冻结供应商配置，防止执行中切换目的地或模型。
- `strategies.transcript` 始终为原始版本；新增 `corrected_transcript`、`ai_review` 列保存独立快照。document 增补 `ai_review` 和 `corrected_segments`，策略及证据增补 `transcript_version: corrected|original`。导出同时带原版、校正版和审计，不含凭据。人工编辑后原草案/审计标为过期，不覆盖原文。
- `ai_review` 保持设计字段 status/summary/changes/questions；changes 的 original/corrected 是整段文本。初版使用保守同音字词表；现已由可见“金融术语主动校正补充修正”组接管语言门控，扩展上下文局部纠错及 rejected_changes 审计，本组不覆盖其修改。模型声明“不确定”的改动不自动应用。校正版引文必须逐字匹配校正版；不得冒称原始转写。
- 候选 `title` 使用 strategy.title，`source_title` 保留资料标题。候选同时提供原始 transcript、corrected_transcript、ai_review、evidence_transcript_version。
- `/api/ai/strategies/{source_id}/mapping` 按设计返回；额外 `confirmed:false` 和 evidence 的 transcript_version 用于明确确认及引文版本。所有问题都使 rules=null、ready=false，不落库也不代勾确认。参数经现有 DSL 以及证据语义双重验证。

## 引擎核实后的重要边界

现有 `ma` 实际执行的是快均线高于慢均线持仓、否则清仓（不是只在交叉事件下单）；`threshold` 是收盘价 <= 买线、>= 卖线，日线信号次日开盘执行。止损基准是策略入场信号收盘价。映射必须与这些边界一致；纯上穿/下穿事件、价格穿单均线、严格小于/大于、分钟/周线、筛选条件、成本价止损不能假装完整支持，必须待确认。未说明止损可无该可选参数，但不能遗漏已给的止损。

## 官方预设来源（2026-11-10 核实）

- OpenAI Chat Completions：https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- DeepSeek：https://api-docs.deepseek.com/ 及 https://api-docs.deepseek.com/updates/ （旧 deepseek-chat/reasoner 已公告退役，使用当前文档模型 ID）。
- Qwen 北京兼容端点：https://www.alibabacloud.com/help/en/model-studio/model-calling-in-sub-workspace （地域/工作空间地址可编辑）。
- Kimi：https://platform.kimi.ai/docs/get-your-api-key （旧 moonshot.ai 文档重定向到此，当前国际站为 api.moonshot.ai/v1、kimi-k3.1-pro；中国站文档本次无法抓取，不声称已核实，地址可编辑）。
- GLM：https://docs.bigmodel.cn/cn/guide/develop/openai/introduction

只实现 OpenAI 兼容 Chat Completions 及已有 Ollama 协议，模型 ID 可手输。保存不代表连通；连接测试真实发送简短文本，供应商返回内容不保存。禁止重定向和环境代理转发凭据。

## 进展与验证

- [x] 读取设计、现有队列、引用验证及实际日线引擎语义。
- [x] 先记录存储及契约增补。
- [x] 实现及有意义的自动化测试：新增 38 项通过（含真实 Windows DPAPI 加解密生命周期；模型 HTTP 使用替身）。
- [x] 全链路：模拟供应商响应 → 原提取接口 → AI 映射 → 未确认组合拒绝就绪 → 人工确认组合 → 回测及模拟回放；两者 fills 相同且非空。

### 已落地接口交接

设计列出的 GET/PUT/DELETE `/api/ai/config`、POST `/api/ai/test`、POST `/api/ai/strategies/{source_id}/mapping` 已实现。管理/映射路由使用真实回环 client IP；TestClient 应显式传 `client=('127.0.0.1',1234)`，不会为测试虚构 testclient 来源豁免。旧提取替身仍支持只实现 `extract(segments)`。

`GET document` 新增 `corrected_segments`（与 ai_review 同策略快照，未生成时 null）；`ai_review.stale` 表示人工改过当前原文。策略每条 evidence 和 strategy 本身标记 `transcript_version='corrected'`；旧草案默认 original。原文查看必须用 `segments`；校正版证据使用 corrected_segments。导出新增 corrected_transcript、ai_review、evidence_transcript_version；现有 transcript 原样保留。

候选返回 `title` 自动策略名、`source_title` 资料名、`corrected_transcript`、`ai_review`、`evidence_transcript_version`。AI 映射返回 `confirmed:false`，无论建议是否 ready 都不会保存组合或确认。用户需要通过原组合 API 确认，原 readiness 继续生效。已有 questions 的草案直接返回问题，不花费一次映射请求。提取开始时冻结配置，切换配置不会混淆两次调用的供应商及模型归属。

预设 model ID 从官方当前文档取示例，可编辑；Kimi 使用已成功核实的国际站而非无法抓取的中国站。`/api/ai/test` 只发极短提示，不保存文本，不使用环境代理、不自动跳转。旧 env 仅在尚未保存过用户配置时兼容；删除会禁用 env 回退。

### 有意保守的映射范围

除 DSL 和引文校验外，规则须能逐句对应：例如“收盘价小于等于10元买入”“收盘价大于等于11元全部卖出”“目标仓位50%”；双均线需明确“5日均线高于20日均线时买入”和“不高于时全部卖出”；可选止损需明确入场信号收盘价基准。完整转写中每个子句也须已覆盖，避免 AI 摘录漏掉 ROE 等筛选项。未识别的叙述、中文数字、复杂措辞同样返回问题，不能宣称自动完整映射。此范围刻意偏保守，人工仍可校对后重提或使用原人工映射流程。

### 验证记录

- 新测试 `tests/test_ai_backend.py`：38 项；完整回归（暂排除同时开发的语言文件）303 passed / 104 既有 warnings，34.38 秒。
- 首轮相关回归（新增当时35项 + adapters/app/validation/trading/phase3）：83 passed。
- 全测试回归首次运行在并行新增 `test_ai_language.py` 的前三个用例失败后停止（53 passed / 3 failed）：当前封闭词表不满足新增真实样例/开放式局部纠错要求。索引显示“金融术语主动校正补充修正”可见工作组正在负责该范围，本工作组不覆盖其 review.py 修正。待该组交付后协调重跑全套。
- 新测试中的网络均为 httpx.MockTransport；没有真实花费用户 API Key。真实服务端点与模型质量尚未验证。

补充修正：只移除由旧验证器自动添加的“未提取到止损”提示；若同样文字原本由模型 questions 明确提出，仍保留并阻止就绪，有单独回归测试。连接测试 OpenAI 使用 max_completion_tokens，其余兼容服务使用 max_tokens；未设置 reasoning 模型可能拒绝的 temperature=0。

## 最终交付状态

本工作组实现与必要自检完成，可供基本验收。并行语言修正已进入当前源码后，本组最终运行：

```powershell
.venv/Scripts/python.exe -m pytest tests -q --disable-warnings --maxfail=3
```

结果：**352 passed，104 个既有 warnings，33.87 秒，退出码 0**。包括本组38项、并行语言49项及既有全套测试。此前 ROE遗漏测试和封闭词表样例失败均已在这次完整运行中通过。测试结束后的本组变动只有本交接文档。

交付包含：DPAPI本机设置与回环管理、官方兼容预设/自定义模型、动态 status、轻量连接测试、校正/摘录/命名管线、原始与校正版本快照/导出、候选策略命名、严格证据和完整语句覆盖的 DSL 映射、confirmed=false及原组合/两运行入口的契约验证。`app/jobs.py` 仅改 extract 块，保留另一工作组 download 分支。

本工作组未重启8765、未修改正式数据/.env/用户凭据、未真实调用用户付费模型。正式部署及最终可见基本验收由协调与验收组执行。真实模型连通性和纠错质量仍需用户选择供应商并提供自己的 Key 后通过实际请求验证，不能由这些替身测试代替。

所有模型质量/协议测试使用明确标记的替身响应；不使用用户 Key，不声称已验证真实模型输出质量或供应商连通。
