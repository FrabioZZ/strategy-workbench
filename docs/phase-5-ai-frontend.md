# Phase 5 — AI 前端工作组

工作目录：`C:/Users/Admin/Desktop/quant`；非 Git，无独立 branch / worktree。范围：`frontend/ai.js`、`frontend/ai.css`、`frontend/trading.js`、AI UI 探针。其他前端入口及后端由相应工作组维护。

## 执行记录

- 已读取 Phase 5 设计与索引；按已授权设计直接实施，不新建聊天或后台代理。
- 使用执行计划、测试驱动及完成前验证流程。当前目录无 Git 且用户指定共享目录，因此不创建 worktree、不运行依赖 Git 的计划脚本；本文件作为进度与接口记录。
- 先建立隔离静态服务和模拟 API 的浏览器探针，验证设置、摘要、参数回填与异步响应失效，再完成实现。
- 接口依赖：入口组挂载 `ai.css` / `ai.js`，提供 `#ai-settings-root`，每次资料渲染后派发 `document-rendered`，`detail` 为完整 document；保存/删除设置后本组调用现有 `refreshConfig()`。
- 审核由协调组组织单独可见基本验收；本工作组只做实现和必要自检。

## 实现结果

- [x] 供应商预设来自 `GET /api/ai/config`；地址和模型 ID 可编辑。Key 使用 password 输入，提交后立即清空；供应商/地址变化清空输入并要求新 Key（Ollama 无凭据例外）。保存、删除、真实请求测试分别调用设计 API，保存/删除调用 `refreshConfig()`。保存状态与本次测试结果分开，HTTP 失败也会替换旧成功状态。
- [x] 校正摘要通过实际 `document-rendered` 事件呈现；详情默认收起，只展示有改动的段落，不展开完整原文。资料切换后清空上一资料摘要。引文与原文不一致时标记校正稿，并将跳转文案改为查看对应原始段落。
- [x] AI 参数生成只用于有来源的草案；使用自动策略标题，额外显示/搜索 `source_title`。调用映射后核对来源 ID/版本，并重新读取候选核对过期状态；返回规则只允许现有 ma/threshold 字段及有效数字。未支持字段、HTTP 错误、版本不符均保留当前输入。
- [x] 完整建议回填参数和说明，`confirmed=false`，显示模型、来源版本、问题和可展开证据。缺项/不支持时规则为 null，禁用确认；用户需补充原文重新提取，或明确手工处理后再确认保存。AI 不自动保存、不自动确认。
- [x] 请求状态独立放在 Map，不序列化到组合。编辑同一项、移除、切换组合、保存会使旧请求失效；一项完成只更新该项，保留其他策略正在输入的值及焦点。
- [x] 浏览器桌面/手机检查、语法检查与证据。

## 接口对齐与范围说明

- 已对齐后端新增的 `evidence.transcript_version`，校正稿证据会在组合中明确标识；旧数据无版本标志时对照原始 `transcript` 判断。
- 文档中的 `changes.original/corrected` 视为整段原文/校正版；`ai_review` 不存在时不展示占位成功状态。
- 入口组已挂载 `ai.css` / `ai.js` 并提供 root/event；浏览器探针报告 `mountedFallback=false`，使用实际 HTML 挂载。
- 实现没有改动 `app.js`、`index.html`、`style.css` 或任何后端文件，未重启 8765，未读取/修改正式数据、`.env` 或用户 Key。
- 沿用既有组合保存接口与 readiness；已验证同一已保存组合出现在回测、模拟盘选择器。实际引擎 API 全链路与正式部署由协调/后端组验收。

## 验证证据（2026-11-10）

命令：

```powershell
node --check frontend/ai.js
node --check frontend/trading.js
node --check scripts/phase5_ai_ui_smoke.cjs
node scripts/phase5_ai_ui_smoke.cjs
```

最终结果：全部退出码 0；浏览器报告 `passed=true`、`errors=[]`、`statusReads=4`、`testCalls=2`、`mountedFallback=false`。静态测试服务器使用随机回环端口；全部 API 返回明确测试替身，不接触生产服务器。页面脚本使用实际入口、实际 DOM 及实际 `renderDocument()` 事件。

覆盖：password 属性与提交清空、不回显 Key、保存不冒称连通、连接成功/HTTP 失败、可编辑模型/地址、保留同地址已有 Key、改地址要求新 Key、删除刷新状态、命名与资料标题、完整/缺项/过期/异常/无效类型/额外未支持条件映射、编辑后旧请求失效、其他项焦点保全、切换组合失效、未确认保存及两运行选择器、摘要默认折叠与资料切换、校正稿引用区分、原始全文默认收起、1440/390/320 像素无横向溢出。

实际发现并经失败→修复→通过验证的问题：测试失败后旧连接成功标记未更新；建议完成重绘全部策略导致其他输入丢失焦点；额外不支持的规则字段被静默忽略。均已修复。

截图和报告：

- [浏览器报告](../output/playwright/phase5-ai-result.json)
- [桌面设置](../output/playwright/phase5-ai-settings-1440.png)、[320px 设置](../output/playwright/phase5-ai-settings-320.png)
- [桌面 AI 参数与证据](../output/playwright/phase5-ai-mapping-1440.png)、[390px 参数与证据](../output/playwright/phase5-ai-mapping-390.png)
- [校正详情](../output/playwright/phase5-ai-review.png)

工作组状态：实现与必要自检完成，待协调组织可见基本验收。无前端接口阻塞。

真实供应商调用尚未验证；浏览器替身测试不代表真实模型连通或质量。
