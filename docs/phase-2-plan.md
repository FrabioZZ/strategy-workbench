# Phase 2 Implementation Plan

> 使用 superpowers:executing-plans 在各可见工作线程执行；本轮沿用用户已指定的可见实现/基本验收流程，不另起隐藏代理。

**Goal:** 从已选策略组合完成本地历史回测和独立模拟跟盘闭环。
**Architecture:** 沿用 FastAPI、SQLite、原生网页；独立 trading 路由、确定性内核、持久化模拟会话；前后端契约先行。
**Tech Stack:** Python 3.12、Pydantic、SQLite、HTML/CSS/JS、pytest、Playwright。
**Spec:** docs/phase-2-design.md。

## Global Constraints

目录 C:/Users/Admin/Desktop/quant，非 Git 仓库，无 worktree/branch，不初始化 Git。A 股优先，日线只做多，手机优先；不新增账户或付费资源，不使用假行情冒充真实数据。保留现有资料导入/提取/媒体功能。账户与外部行情凭证不进入浏览器、日志或文档。

## Review Focus

过期策略绑定与冻结快照；同根行情未来泄漏；禁用项/无效权重实际参与运算；模拟重复消费与重启恢复；导航切换未保存资料及窄屏溢出。各项必须有业务行为测试或浏览器检查。

## Task 1：后端执行闭环

Owner：Phase 2 - 策略执行、回测与模拟账本实现。
Files：app/trading/ 新包、app/main.py 挂载、必要配置、tests/test_trading*.py、docs/phase-2-api.md、docs/phase-2-backend.md；不修改 frontend/。

- [x] 先定义并写出 API 契约，含请求/响应示例、校验错误、所有前端需要的字段。
- [x] 测试先覆盖组合开关/权重/版本/确认状态，然后实现资源与存储。
- [x] 测试 CSV 校验、下一根撮合、费用复算、现金/整手/T+1，再实现引擎。
- [x] 测试独立账本、重复行情幂等、暂停重启、过期数据，再实现模拟会话与行情适配边界。
- [x] 运行新增后端及历史 pytest 测试，记录命令、测试数、已实现与外部待联调边界。环境沙盒若导致 TestClient 挂起采用有界诊断；不反复无限等候。

## Task 2：四模块前端

Owner：Phase 2 - 策略筛选与回测模拟盘界面实现。
Files：frontend/、scripts/phase2_ui_smoke.cjs、docs/phase-2-frontend.md；仅必要时新增测试 UI fixture 文件，不改后端。

- [x] 等待 Task 1 发布契约后读取，完成手机 Dock / 桌面导航与模块切换。
- [x] 实现草案多选、手工映射确认、勾选/权重模式、冲突选择、保存组合与就绪反馈。
- [x] 实现 CSV/演示数据、参数与运行回测、真实结果曲线/表格/费用明细。
- [x] 实现模拟会话创建、启动暂停同步、最新状态、订单持仓；清晰区分回放/增量跟盘/未接券商。
- [x] 真实后端下浏览器主流程验收，手机与桌面截图、console错误检查，既有资料流程回归。

## Task 3：独立基本验收与修复

Owner：独立可见基本验收聊天，必要时另建可见修复聊天。
Files：docs/phase-2-review.md；修复文件视发现指定，避免与实现并写。

- [x] 等两实现完成后，按 spec 逐条验证主流程、实际运算和明显回归。
- [x] 协调收集结果，必要修复并复验；不默认对抗审计。
- [x] 更新 PRODUCT.md、README.md、阶段索引与最终接受状态，区分完成的本地功能、外部接入限制。

最终结果：本地 MVP 接受，145 pytest通过，手机/桌面及原资料媒体回归通过；协调时钟补查已单独修复并复验。详见阶段索引，外部真实行情/券商/模型联调不包含在通过声明中。
