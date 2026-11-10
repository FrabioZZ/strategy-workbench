# Phase 7 — 最终产品校准、发布与 PPT 同步

协调聊天：`01a1c5ee-a547-7f53-b4ca-e8aee5c4a90d`。所有应用工作复用 `C:/Users/Admin/Desktop/quant`，分支 `main`，无新增 worktree。

## 用户确认的范围

- 一进二仅是功能测试样例，不是产品定位或整体交易策略的验收目标。删除通用界面的相关验证说明。
- 产品按提取并确认的交易策略分析行情指标、执行交易，最终结果以盈亏为核心；不做打板等盘面预测验证。
- 清除注释性灰色小字、开发实现叙事与重复说明；保留实际参数、操作状态和错误反馈。
- 使用 Hallmark、Open Design、UI/UX Pro Max / Taste 技能校准既有 UI，使 demo 可供用户直接使用。
- 基本验收后提交现有 GitHub 仓库、打包新版本，再授权与“quant项目ppt”聊天同步应用截图和内容。
- 当前实现仍是历史回测和模拟交易。本轮不新增券商真实下单、不修改用户资料、策略或账本。

## 可见工作组

| 聊天 | ID | 文件职责 | 状态与检查点 |
|---|---|---|---|
| Phase 7 - 最终产品校准、发布与 PPT 同步 | 01a1c5ee-a547-7f53-b4ca-e8aee5c4a90d | 产品文档、发布、便携包、PPT交接 | 进行中 |
| Phase 7 - 用户级界面校准与文案清理 | 01a1c5f4-fcd9-7331-a0b8-5a5627a42106 | frontend、UI smoke、phase-7-ui.md | 实现完成，五种宽度和主要流程自测通过 |
| Phase 7 - 用户流程与界面基本验收 | 01a1c5f6-cde7-7ae1-8336-a637c90f720d | phase-7-review.md | 通过；432 Python、2 Node及浏览器主流程，无剩余必修项 |
| 制作 Quant 项目介绍 PPT | 01a1c5d7-83f1-7c40-a905-5d52ee96e766 | 独立 PPT 项目 | 已按用户授权交接；准备文案，等待发布后重抓界面 |

## 执行与验收计划

沿用原生 HTML/CSS/JS、FastAPI/SQLite 和当前指标执行引擎。界面按“资料 → 策略组合 → 回测 / 模拟 → 盈亏”组织，不为视觉改动迁移技术栈。

- [x] 实现：获取并阅读点名技能，清除验证样例叙事和注释小字，统一控件、表单、空态与结果层级。
- [x] 功能：隔离数据运行策略编辑、确认、日期范围、回测盈亏、模拟交易与刷新恢复；确认错误状态仍可见。
- [x] 布局：桌面与 390/320px 手机无横向溢出，键盘焦点可见；盈亏先于技术详情。
- [x] 基本验收：独立可见聊天检查主流程，修复必要问题，不扩展对抗审计。
- [x] 打包：更新版本与用户说明，复用已验证运行时，校验源码清单、ZIP、独立目录启动/退出。
- [ ] 发布：检查提交文件不含用户数据/Key，提交并推送私有仓库，创建可下载版本并核验哈希。
- [ ] PPT：向已授权聊天交接最终界面/截图路径和产品口径，跟进修改与成品验收。

现有未提交 `docs/phase-5-index.md` 为此前工作，保留；本阶段不覆盖其内容。最终接受状态与发布证据待补。

发布目标：`v0.6.1`，沿用私有仓库 `FrabioZZ/strategy-workbench`，保留旧版本附件。已有 GitHub 系统钥匙串凭据有效；受限进程无法读取钥匙串造成的初始失效提示已通过系统环境只读核验排除。

## 便携包与本机验收

- 新包 `output/StrategyWorkbench-0.6.1-windows-x64.zip`，758679966 字节，SHA256 `9583edda8e55767c778889fe1c9a4d7dbecc57b789fc695ea8a2d7817ec09b66`。
- ZIP 共 11440 文件，完整 CRC 通过；清单中 61 个应用/前端/启动文件逐个与源码哈希一致，没有打入 user-data 或 .env。证据：`.runtime/phase7-release/archive-check.json`。
- 从实际 ZIP 解压至 `.runtime/phase7-relocation/StrategyWorkbench-0.6.1-windows-x64`，内置 Python 依赖、无控制台启动、ASR 模型加载、300股/203572行导入、32指标、媒体解析子进程、Chromium及停止程序全部通过。证据：`.runtime/phase7-relocation/portable-verification.json`。
- 8765 继续使用现有服务，新版静态文件直接生效；只读取得的首页和5个主要资源与源码字节一致。
- 正式 `documents/jobs/strategies/resources` 四张表行数与内容 SHA256 前后相同（3/4/0/1）。证据：`.runtime/phase7-release/data-before.json`、`data-after.json`。

源码已通过[独立基本验收](phase-7-review.md)：432 项 Python、2 项 Node、转写状态及四组浏览器流程通过。89 个应用/前端/测试文件在验收前后保持一致。不存在本轮待修复项，发布上传及 PPT 最终接受仍待下方记录。
