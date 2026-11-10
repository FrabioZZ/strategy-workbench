# Phase 7 — 最终界面校准实现记录

日期：2026-11-10（Asia/Shanghai）。实现聊天：`01a1c5f4-fcd9-7331-a0b8-5a5627a42106`；协调聊天：`01a1c5ee-a547-7f53-b4ca-e8aee5c4a90d`。

工作目录：`C:/Users/Admin/Desktop/quant`，分支 `main`，复用现有 checkout。实现已完成，等待独立基本验收。本聊天未创建子线程、后台代理或 worktree，未操作正式数据、重启 8765 服务、commit、push 或打包。协调与发布文件的同期修改由协调聊天负责。

## 范围与结果

- 保留资料、策略组合、回测、模拟盘四工作区，以及既有表单 ID、导航、API 和执行引擎。
- 从通用指标库删除“一进二：日线验证边界”整块。首个涨停预设仅保留指标条件、下一交易日执行时点及每日限价数据要求，不再承担产品定位。
- 首页改为“从资料提取交易策略”，工作流明确为资料提取、参数核对、行情分析、回测与模拟交易。仍明确未接入券商实盘。
- 回测、日线模拟、独立 Backtrader 回放均首先显示阶段盈亏和收益率。初始/结束资产、回撤、费用和交易笔数作为次级信息。
- 计算口径、数据覆盖、复权限制、冻结参数、委托、信号和完整净值使用原生 `details` 展开。模拟运行状态、行情错误、未就绪条件和演示数据标签继续可见；没有使用 `.helper { display:none }` 等全局隐藏来删除状态。
- 删除或精简首页、资料面板、策略编辑、模拟配置中的重复说明。费用参数、授权发送模型内容、有效日期范围、错误与状态保留。
- 新增 `frontend/product.css` 统一字体、内容宽度、主次控件、指标层级、表格与 320/390 像素响应式。独立模拟模块原有暖色硬编码改为项目蓝灰 token。
- 净值图坐标改为 HTML 文本，手机缩放时仍可读；仅一根日线时显示该日资产，避免空白曲线。可横向滚动的账本保留首列定位。
- 运行完成与选择历史回测后聚焦结果。异步按钮带 `aria-busy`，详情展开状态在模拟刷新后保留。清空历史回测或独立回放选择会清除旧结果。修复独立引擎刷新按钮小于 44px 的触控高度。

## 实际读取的指定技能

技能均下载到项目 `.runtime/phase7-skills`，没有安装到全局目录。四份 SKILL.md 的来源、版本及 SHA-256 存于 `output/playwright/phase7/skill-provenance.json`。

| 技能 | 实际来源与读取参考 | 本轮采用点 |
| --- | --- | --- |
| HallMark 2.0.0 | [Nutlope/hallmark](https://github.com/Nutlope/hallmark/tree/main/skills/hallmark)，读取 `SKILL.md`、`redesign.md`、`flow.md` 的 App screens / Harnesses、`gates.md`、`craft.md` 控件/表格部分、`patterns.md` | 项目 DESIGN.md 优先；保留接口与工作区；应用界面不套营销 hero；克制颜色、统一控件、数值层级、键盘焦点、减少装饰和重复文案。 |
| Open Design | [sugarforever/open-design-skill](https://github.com/sugarforever/open-design-skill) 与 [nexu-io/open-design](https://github.com/nexu-io/open-design)，内容提交 `b4ec310921f49ae512de1f0a1f3a4e7ce3d05f2f`；读取 dashboard 模板、application 设计规范、state-coverage、accessibility-baseline、laws-of-ux | 采用主指标—图表—表格顺序、状态恢复、原生控件、渐进展开。application 的紫色、模板示例数据和额外导航与用户要求不符，未采用；保留项目既定蓝灰与真实引擎数据。 |
| UI/UX Pro Max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max)，读取 `SKILL.md`、`quick-reference.md`、`pro-rules.md` | 原生 HTML/JS；重点采用键盘导航、可见焦点、触控高度、手机输入字号、加载/禁用状态、减少非必要动效。`keyboard focus navigation --domain ux` 命中对应规则；渐进展开查询及一次重试返回不相关标题规则，未将其当作有效命中，展开结构依据 Open Design 和用户要求。 |
| Taste 2.5.1 | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill/tree/main/skills/taste-skill)，读取 `SKILL.md`，以及 copy、copy-voice、system 的适用文案/一致性部分 | 具体名词标题、动词+对象操作、统一文字与间距、真实信息、去掉解释性重复。该版本主要为展示型网站，不采用整屏 hero、照片、shader、抽签主题或营销动效。 |

用户已授权直接最终修复并保留现有设计，因此不重新发起样式选择/设计审批，也不启动 Open Design 服务或 Taste 营销网站完整流水线。未声称四技能全部检查或所有规则均已执行。

HallMark 下载成功；Open Design git 默认 Windows Schannel 克隆失败后，通过单次 `git -c http.sslBackend=openssl` 克隆成功，没有修改全局 Git 配置。Taste 正确技能路径是 `skills/taste-skill`，根目录安装尝试没有 SKILL.md 后改用该路径成功。

## 文件

- `frontend/index.html`：入口文案、工作区说明、折叠辅助内容、新样式入口。
- `frontend/product.css`：最终界面样式与响应式校准。
- `frontend/trading.js`：指标叙事清理、结果层级、数据详情、净值图、结果聚焦及清空历史选择。
- `frontend/app.js`：资料及转写说明精简。
- `frontend/paper-external.js`、`frontend/paper-external.css`：独立引擎回放盈亏优先、文案、统一色彩及空态。
- `frontend/quotes.js`、`frontend/quotes.css`：报价说明收短，涨跌颜色改用项目 token。
- `scripts/phase6_ui_smoke.cjs`：将旧“一进二/无法验证打板”断言改为新产品叙事断言，保留原功能验证，增加 Phase 7 模式。
- `scripts/phase7_ui_smoke.cjs`：复用既有真实 API/引擎流程的 Phase 7 入口，避免维护两份重复脚本。

## 验证证据

最终执行 `node scripts/phase7_ui_smoke.cjs` 通过，完整结果：`output/playwright/phase7/phase7-ui-result.json`。

- 隔离数据目录：`.runtime/phase7-ui-1794323125111`。测试临时端口由系统分配并断言不等于 8765，服务通过自身 stdin 正常关闭。
- 32 个指标，MACD/BOLL/KDJ/EMA/量比/首个涨停预设，非法 JSON、未来偏移、人工确认状态、AI 参数响应兼容与无效响应保留现有值。
- 真实本地研究回测：2024-02-13 至 2024-04-02，预热 30 根，初始资产 10,000.00，结束资产 10,743.74，阶段盈亏 +743.74。核对请求日期、实际日期、持久化结果和界面金额。
- 真实未复权回测与日线模拟账户创建、单步执行；模拟请求未误带回测起止日。
- 真实 Backtrader 创建并运行全部 80 根人工行情，结果盈亏与引擎净值核对，`externalEngineVerified: true`。
- 1440 / 1024 / 768 / 390 / 320 像素，四工作区无页面横向滚动，另检查表单与按钮实际边界，避免 `overflow-x:clip` 掩盖控件溢出。可见可用按钮高度 ≥43px（44px 目标，允许亚像素误差）。
- 键盘切换工作区、导入 tabs、Enter 展开计算口径，模拟刷新后展开状态保留，reduced-motion 环境；真实文本导入成功，原文默认折叠；注入数据服务 503 后保留可见错误和刷新入口。
- 浏览器 `pageerror` 数量为 0。

AI 专项回归 `node scripts/phase5_ai_ui_smoke.cjs` 通过：`output/playwright/phase7/ai-ui-result.json`（fixtureOnly=true）。覆盖设置保存/删除/失败、供应商切换、手工参数确认、异步映射期间其他编辑焦点、来源版本、原文/校正稿折叠。

`node --check` 对本次修改的四份 JS 通过；`git diff --check -- frontend scripts/phase6_ui_smoke.cjs scripts/phase7_ui_smoke.cjs` 通过。

技能检查结果：

- HallMark `sloplint` 对 `frontend/index.html` 与新增 `frontend/product.css`：0 FAIL / 0 REFLEX / 0 WARN，见 `output/playwright/phase7/hallmark-static.txt`。**仅此二文件的静态检查**；其 render tier 因本地缺少 puppeteer-core 未执行，不声明 HallMark 浏览器检查通过。实际浏览器检查使用项目现有 Playwright。
- Taste `copy-lint` 对入口 HTML：0 FAIL / 1 WARN，见 `output/playwright/phase7/taste-copy.txt`。WARN 把资料数量 0 与工作步骤 1/2/3 识别为 stat strip；保留，它们是真实空库数量和操作步骤，不是虚构指标。

## 截图索引

目录：`output/playwright/phase7/`。已查看桌面首页/回测与手机资料、策略编辑、模拟结果，所有截图为隔离人工数据。

- `phase7-materials-1440.png`、`phase7-materials-390.png`、`phase7-materials-320.png`
- `phase7-portfolio-1440.png`、`phase7-portfolio-390.png`；`phase7-conditions-320.png`
- `phase7-backtest-1440.png`、`phase7-backtest-390.png`、`phase7-backtest-320.png`
- `phase7-results-1440.png`、`phase7-results-390.png`、`phase7-results-320.png`：研究回测盈亏摘要
- `phase7-paper-result-1440.png`、`phase7-paper-result-390.png`、`phase7-paper-result-320.png`
- `phase7-external-result-1440.png`、`phase7-external-result-390.png`：独立引擎真实运行结果
- `phase7-imported-material-390.png`、`phase7-data-error-390.png`

相应工作区另有 1024/768 像素截图。长页面截图包含手机固定底栏在截图时的视口位置；页面预留底部安全区，实际交互由浏览器验证。

## 限制与交接

本轮是前端产品校准，不新增交易模型或供应商能力。行情与 AI 响应使用明确标识的人工夹具，公开报价请求在测试页被隔离路由拦截，没有新增真实行情、视频或模型联网验证；不能由此声称真实券商交易或策略获利能力。正式数据未改动。独立基本验收、GitHub 提交、便携包及 quant项目ppt 同步由协调聊天继续执行。
