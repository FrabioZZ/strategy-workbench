# Phase 2 前端实现记录

计划：docs/phase-2-plan.md Task 2。范围：frontend/、scripts/phase2_ui_smoke.cjs；复用目录，无 Git/branch。

## 执行记录

- 已读取设计与现有一期前端。接口依赖后端线程发布 docs/phase-2-api.md。
- Ruling: 按用户明确授权直接执行；复用非 Git 目录、在本文件记录进展；不运行依赖 Git 的技能工作区脚本。独立基本验收由协调线程指定的可见聊天执行，不另起代理。
- Ruling: 浏览器测试沿用仓库的 Playwright Node 脚本，复用显式测试提供方与隔离数据；真实交易接口不使用测试替身。
- 导航/深链/未保存转写保留行为测试先行；开始实现前预期因无四模块导航失败。

## 当前状态

前端实现与本线程浏览器主流程验收完成。阶段最终接受状态由协调线程安排独立可见基本验收后确定；未做对抗审计。

## 已实现

- 四个完整工作区与 hash 深链；手机固定底部 Dock、桌面侧栏；资料区 DOM 不销毁，未保存校对可跨模块保留。
- 多草案搜索、原规则证据、显式选择执行器、手工规则、启用开关、滑杆/数字权重、均分/归一化、冲突策略、参数变动后撤销确认、保存与就绪问题。
- CSV 上传、模板下载、真实数据范围确认、演示行情明确标识；组合版本/初始资金/费用滑点/历史回测；净值 SVG、费用、现金、持仓、成交、委托原因与信号分歧。
- 独立模拟页：历史回放/盘后增量、CSV/Tushare 状态、账户列表、启动暂停同步单步、5 秒状态刷新、心跳行情游标、资金与完整账本。
- 外部 JS/CSS，无外部 CDN、无内联脚本样式；按现有设计 tokens 延续浅色表面与蓝色操作。

## 验证过程

- 初始导航测试 RED：Playwright 3 秒超时找不到 `[data-workspace="portfolio"]`，符合实现前缺少导航的实际行为。
- `node --check frontend/trading.js` 与 `node --check scripts/phase2_ui_smoke.cjs` 通过。
- Windows 沙盒内 Python 服务启动无输出，使用已授权的隔离沙盒外测试；Playwright 自带浏览器未安装，改用已安装 Chrome channel，无需下载浏览器。
- 新增 smoke 脚本复用 `tests/ui_server.py`，交易接口保持真实，旧资料 AI/下载/ASR 是测试文件明确的替身。
- 一期回归已通过：`NODE_PATH=<bundled modules> PLAYWRIGHT_CHANNEL=chrome node scripts/ui_smoke.cjs`，本地 WAV/视频播放、历史证据定位、缓存与失败重试、资料编辑提取导出、过期与持久化、手机布局均通过，0 page errors。已人工查看手机截图，资料与新底部 Dock 正常。

## 最终验证

- `NODE_PATH=C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`，使用同 runtime 的 `node.exe scripts/phase2_ui_smoke.cjs`（本机 Chrome，独立 8767 端口，隐藏子进程，运行后关闭自身测试服务）。最终 exit 0。
- 通过：四区切换/hash 刷新/键盘跳转；320、390、1440 宽度无页面横向溢出；资料未保存转写跨区保留；候选草案不自动映射；两手工策略、权重就绪失败、显式归一化与保存；CSV 导入和演示行情；真实回测净值/费用/成交；模拟历史回放单步、启动、同步、暂停；无新行情账户不成交；新账户不继承前账户 CSV 选择。
- 本次构造 CSV 的真实引擎计算为 2 笔成交、118.12 元费用；无行情增量账户 0 笔成交、现金 100000 元。测试数据是隔离环境中明确标注的人工构造数据，不作为真实市场收益展示。浏览器 console/page errors 为 0。
- 最终证据：`output/playwright/phase2-result.json`。测试目录 `.runtime/phase2-ui-1794238760668`，未使用用户数据。
- 截图：`output/playwright/phase2-mobile-portfolio.png`、`phase2-mobile-backtest.png`、`phase2-mobile-paper.png`，以及对应 `phase2-desktop-*.png`。已人工检查资料手机、组合桌面、回测手机和模拟盘手机/桌面截图。
- 最终 JS 语法检查通过：`node --check frontend/trading.js` 与 `node --check scripts/phase2_ui_smoke.cjs`。

## 验收中修复

- 回放同步误携带其他选择的数据集，后端返回 409：同步固定使用冻结数据，并禁用回放数据切换；回归验证游标从 01-06 推进到 01-07。
- 新账户继承前账户同步 CSV：新增断言先失败，修复会话选择更新顺序后通过。
- 键盘跳转链接被 hash 路由识别为资料区：新增断言先失败，改为只聚焦主内容且保留 hash；保持键盘可聚焦性并通过复验。
- 浏览器 favicon 404：补充本地 SVG 站点图标。导航测试增加等待 hashchange 渲染，消除测试时序竞争。

## 边界与未完成内容

- 本线程分配的前端工作无阻塞或未实现项；后端规则时钟与会话持久化由后端测试和独立基本验收负责。
- Tushare 真正接入、外部行情授权、券商连接及常驻运行均未联调/未配置；页面明确显示实际状态，不宣称实时交易。云迁移与原生客户端不属于本阶段。
- 所有资料 AI/ASR 成功测试由一期显式测试替身提供；不代表用户已配置真实模型。交易数据导入、组合、回测、模拟接口与账本全部使用真实后端。
