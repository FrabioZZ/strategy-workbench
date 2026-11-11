# Phase 8 — 金融视频语音转写升级

协调聊天：`01a1c89a-52cc-7d60-8029-ee09c2d93417`（Phase 8 - 金融视频语音转写升级协调）。来源聊天：`01a1c88c-34f4-74c2-9097-9b3aff73bf45`；用户已授权“接入Phase8进行推进”，无需重复开工批准。

工作目录 `C:/Users/Admin/Desktop/quant`，分支 `main`，复用现有 checkout，无新 worktree。保留既有 `app/ai/client.py`、`docs/phase-5-index.md`、`tests/test_ai_client.py` 改动，不计入本阶段成果。

## 范围和设计决策

接入 Qwen 文件 ASR、金融词表和主题上下文，保留本地 small。独立 ASR 凭据与本机加密设置，正常入口展示供应商/模型、错误和重试；缓存复用、原始转写/时间戳/校对审计保留。历史资料通过可追溯副本重转写，不覆盖已有策略证据。优先完成无凭据可验收接入；真实云识别精度必须用授权样本和 Qwen Key 单独核验，不自动付费调用。

## 可见工作组

| 聊天 | ID | 目录/分支 | 职责 | 状态 |
|---|---|---|---|---|
| Phase 8 - 金融视频语音转写升级协调 | 01a1c89a-52cc-7d60-8029-ee09c2d93417 | quant / main | 索引、设计边界、官方接口核验、最终接受 | 接入与基本验收结束，真实云对照待 Key |
| Phase 8 - Qwen文件转写与金融上下文实施 | 01a1c89d-af69-7950-b4bd-fd82b4bd3d13 | quant / main | 后端、设置UI、缓存副本、测试和实施记录 | 实施及自测完成，交独立验收 |
| Phase 8 - 转写主流程基本验收 | 01a1c8a2-4fad-7c81-b9f0-d2094d3b60a9 | quant / main | 需求、主要流程、明显回归及验收记录 | 通过，未发现必修项 |

## 检查点

- [x] 接手并核对现有代码/未提交改动；当前 small 无金融上下文。
- [x] 官方 API 的模型、地域、认证、上传、异步查询和时间戳合同核实。
- [x] [设计](phase-8-design.md)、[实施计划](phase-8-plan.md)及[验收清单](phase-8-review.md)落盘，最终一致性随验收复核。
- [x] 后端/设置UI/历史副本/正常入口实施及针对性回归。实施 452 项 Python 回归、浏览器转写回归、普通及 portable 启动、本地 small 正常入口实跑，详见[实施记录](phase-8-implementation.md)。
- [x] 独立基本验收及本机启动兼容。452 项 Python、3 项 Node、隔离 portable 启停通过；浏览器通过真实本机后端和模拟云响应验证配置、重启、续查及历史证据。未发现需修复的主流程问题。见[独立验收](phase-8-review.md)。
- [ ] 真实 small/Qwen 对照（需授权样本与独立 Qwen 凭据，不能用 mock 替代）。

## 阻塞与接受状态

2026-11-11：已建立阶段记录，实施与基本验收准备聊天均已启动。只读检查加载环境后的 `ASR_API_KEY`、`DASHSCOPE_API_KEY`、`QWEN_API_KEY` 均不存在；未读取或借用文本 AI 凭据，缺 Key 不阻塞独立实施。

官方概览推荐 `qwen-audio-3.1-asr-flash-filetrans`；旧 `qwen-asr-api-reference` 仍展示 `qwen3` 及 `file_url`。初次英文 Fun-ASR 搜索快照出现新版合同，但中文 Fun-ASR 页已拆分；实施与验收进一步定位到 [新版专属 HTTP API](https://help.aliyun.com/zh/model-studio/qwen-audio-asr-filetrans-http-api)，据此核实 `file_urls` 数组、`input.context` 与 `parameters.vocabulary`，不混用旧字段。[提升准确率](https://help.aliyun.com/zh/model-studio/improve-asr-accuracy)、[临时上传](https://help.aliyun.com/zh/model-studio/get-temporary-file-url) 一并核验。临时上传不是长期生产对象存储方案，单机试用的限制应写入设计和设置说明。

现有授权金融媒体：480.885 秒、1 条音轨、20644528 字节。协调只读保存既有转写快照和媒体 SHA256 至 `.runtime/phase8-evaluation/existing-transcript-baseline.json`。该历史资料没有引擎元数据，不能声称它是已验证的 fresh small 基线；尚未运行任何真实云识别，质量对照仍待完成。

协调另以修改前的本地 ASR 运行同一媒体，143.61秒完成，282段，保存 `.runtime/phase8-evaluation/fresh-small-baseline.json`。明确为 faster-whisper-small / CPU / int8 / 无领域提示的实跑基线，未修改正式资料，尚未人工计分。正式 documents/strategies 的内容校验快照另存 `formal-data-before.json`，供阶段结束核对。

协调复核正式库时发现新增一份资料和一条策略。按原字段匹配后，阶段开始时的五份资料与两条策略仍逐字节匹配起始哈希，保留新增记录。

后续真实对照使用该媒体的同一 SHA256，先按原音记录参考文字与起止时间，再比对两个引擎的原始识别。分别记金融术语、股票代码、价格、百分比和买卖方向的正确、错写、漏写及新增，并核对抽样片段时间戳。源音频未提及的项目标注不适用。保留两份原始识别与人工对照记录，校正稿另列。

最终接受：本地接入和无凭据基本验收通过。真实云连通性、计费与同段识别精度待用户在「运行配置 → 语音转写服务与金融词表」填写对应地域的独立百炼 ASR Key 后验证。默认继续使用本地 small。隔离 portable 使用上一版随包运行时和更新源码，发布 ZIP 未重建。临时 OSS 用于本机低并发转写。无 GitHub 发布、券商实盘、PPT 或其他阶段扩展授权。
