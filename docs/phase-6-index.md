# Phase 6 — 指标执行与全系统发布协调

协调：01a1c5d2-ffb5-7e31-958b-e559c07f63e1。工作目录均为 `C:/Users/Admin/Desktop/quant`；复用当前目录，无独立 worktree；初始非 Git，已由协调初始化为 `main`。目标：2026-11-10 23:00（北京时间）前完成核心收尾。

## 约束与设计

- 回测可指定起止日期，仅计算区间交易及盈亏，起日前行情只可用于指标预热。
- OHLCV 与常见技术指标统一注册、验证、计算，回测和模拟盘共用执行条件。
- AI 必须对照实际能力映射，未知指标和缺失规则不能伪称可执行；用户仍确认规则。
- 一进二使用真实视频核对，区分日线可运行确认版本和盘中尚不支持条件。
- Windows 便携包内置 Python、依赖、ASR 模型、匿名浏览器和缓存路径；用户只配置 LLM Key。
- GitHub 交付源码和版本软件，不包含用户视频、数据库、Key、浏览器个人资料。
- 做基本验收，不扩展为对抗审计。用户已授权执行及最终 GitHub 发布，省略重复设计批准。

## 可见工作组

| 聊天 | ID | 所有权 | 状态/检查点 |
|---|---|---|---|
| Phase 6 - 指标执行与全系统发布协调 | 01a1c5d2-ffb5-7e31-958b-e559c07f63e1 | config、启动/打包、GitHub | 进行中；便携启动与依赖验证 |
| Phase 6 - 技术指标与策略执行实现 | 01a1c5d4-29ab-7eb0-9732-1f78d867752f | app/trading、对应测试 | 进行中；指标、日期、收益、共用执行 |
| Phase 6 - 回测日期盈亏与指标界面 | 01a1c5d4-350a-70c0-a0db-866a2f759e39 | trading.js 与相关前端块 | 进行中；浏览器主流程 |
| Phase 6 - AI指标映射与一进二验证 | 01a1c5d5-1726-70c3-ac1d-49389c171d26 | AI 映射/能力、对应测试 | 等 Phase5 mapping 交接；视频逐项核对 |
| Phase 6 - 全系统基本验收与发布检查 | 01a1c5d9-7512-7a41-a9d3-6d776aa6e21f | 独立只读验收 | 进行中；需求/主流程/包配置/明显回归 |

Phase5 协调 01a1c5bd-e854-7802-aa57-6d2136626d00 已收到用户授权的同步消息；双方共享源码但各自文件边界明确。当前 GitHub CLI 凭据失效，GitHub connector 仍能访问 FrabioZZ，尚无本项目仓库。

## 执行计划与验收

- [x] 指标与区间回测实现、单元/接口验证。
- [x] 前端起止日期/盈亏/能力展示与浏览器验证。
- [x] AI能力对照、一进二真实文本差距和日线执行验证。
- [x] 便携软件复制运行环境、模型、公共历史数据，自动初始化缓存和本地库。
- [x] 独立基本验收及必要修正；全量回归。
- [x] 新位置启动便携包，验证 API、模型加载、媒体子进程及无手动路径配置。
- [x] 本地 Git 提交、GitHub 上传/发布可下载包，核验远程。
- [ ] GPT Dot 狗头军师通知：尝试检查桌面入口和Pets连接；Pets连续两次传输失败，未能验证单独推送，改在本聊天明确告知，不伪称已送达Dot。

## 决策记录

- 采用便携目录而非单文件自解压，减少大型 ASR 模型重复解包；双击 EXE 启动本地工作台。
- 使用当前已验证 Python 3.12 运行环境及依赖的独立副本，包不依赖本机 venv 或 Codex 路径。
- 源码仓库默认私有，避免无明确公开意图的对外公开；用户资料与凭据不入库。
- 22:26 便携 Python 在隔离模式成功导入全部主依赖；包内 faster-whisper-small CPU/int8 成功加载。便携服务启动成功，ASR 自动 ready，首次自动导入 300 只股票 / 203572 根历史日线。
- GitHub CLI 刷新因权限自动审批被拦截一次，用户随后明确批准恢复已有权限；现处 GitHub 身份复验。

## 最终功能接受与发布候选（22:39）

实现三个工作组全部交付，独立基本验收通过，见 [review](phase-6-review.md)。432项Python测试、Node 2项和独立浏览器主流程通过；无剩余必修缺陷。最终真实注册表为32项（早期进度曾统计35个字段，已纠正）。

正式8765服务已备份并更新。更新前后 `documents/jobs/strategies/resources` 四张表行数及内容SHA256全部一致：3份资料、4个历史任务、0条正式策略、1份历史数据资源；无活动任务被中断。证据在 `.runtime/phase5-deployment-20261110/phase6-before.json`、`phase6-after.json`。

发布包 `output/StrategyWorkbench-0.6.0-windows-x64.zip`，758677969字节，SHA256 `caf97f7e56c5b13fe62388b342f1421e2a37f2f5f4f4cdbf8c0b5602fb6d66fd`。11439个文件、完整CRC通过；无.env、正式数据库或user-data。实际解压到 `.runtime/phase6-relocation/` 后，内置Python依赖、pythonw启动、300股203572行自动导入、32指标API、媒体worker、ASR模型加载、Chromium启动、StopWorkbench退出全部通过。报告 `.runtime/phase6-relocation/portable-verification.json`。

真实《一进二》完整盘中策略仍不支持，原文缺项不会丢弃；明确独立的日线确认版已通过三条执行路径。无真实LLM Key，所以真实供应商连通与模型质量不冒称已验证。当前接受的是日线研究与模拟软件交付，边界在页面、README和Release说明中保留。

Git候选202个文件检查未发现凭据、用户媒体、数据库或大文件；源码/Release将发布至用户自己的私有仓库。GitHub上传与Dot通知的最终结果在后续记录补齐。

## GitHub 最终交付（22:41:43 +08:00）

- 私有源码仓库：https://github.com/FrabioZZ/strategy-workbench
- 发布源码提交：`aa49374`，`main`，标签 `v0.6.0`。
- Release：https://github.com/FrabioZZ/strategy-workbench/releases/tag/v0.6.0
- ZIP：https://github.com/FrabioZZ/strategy-workbench/releases/download/v0.6.0/StrategyWorkbench-0.6.0-windows-x64.zip
- GitHub 附件状态 `uploaded`、大小758677969、服务端SHA256与本地一致；Release `isDraft=false`，publishedAt `2026-11-10T14:41:43Z`。
- 包内60个应用/前端/启动文件的SHA256与已提交源码逐一一致。最终ZIP实际重定位运行验证全部通过。
- 全系统日线版开发、基本验收、本机部署、源码提交及便携包发布均已完成，早于23:00。完整原视频盘中策略与真实LLM质量边界仍按上述说明保留；Dot通知未能单独验证送达。
