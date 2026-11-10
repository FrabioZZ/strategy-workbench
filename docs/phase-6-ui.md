# Phase 6 — 回测区间、结果与指标前端

工作组：Phase 6 前端实施。共享目录 `C:/Users/Admin/Desktop/quant`，非 Git，branch/worktree 不适用。范围：`frontend/trading.js`、必要的 `frontend/trading.css`、`scripts/phase6_ui_smoke.cjs` 和本记录。保留 Phase 5 AI 映射、校正摘要及转写体验。不新建线程/代理、不联系其他线程、不改正式数据、不重启服务。

## 实施结果

- 回测和研究回测增加起止日期，默认读取数据集/股票实际覆盖，区间随运行请求提交。
- 结果显示实际运行区间、初始资产、结束资产、阶段盈亏金额及收益率；历史记录兼容使用最后净值计算，不将未知金额伪装为 0。
- 已按 `docs/phase-6-engine.md` 接入 `conditional` DSL：从 capabilities 读取 32 项指标及参数默认值、范围、公式、预热、仅未复权数据标记。提供 RSI、MACD、布林带、KDJ、EMA、均线+量比、首板后次日开盘意图 7 个预设。使用者可查看中文条件解释，或展开高级 JSON 编辑指标与条件。
- 条件 JSON 校验未知指标/字段、参数类型及范围、禁止未来 offset、树大小与深度；无效内容保留在 UI 草稿中，禁止确认和保存。重绘后仍保持错误与禁用状态。服务保存继续作为最终校验。
- 保留原 MA、threshold 与 AI 映射流程；扩展 AI 回填接受经过同一校验的 conditional，兼容后端补齐的 `field: close`、`offset: 0` 默认参数。建议仍需手动核对确认，不自动保存；额外未支持条件不静默丢弃。
- 一进二只标识日线可验证部分，盘中封板/排板/撤单等不能凭日线验证；不声称真实视频自动全链路通过。
- 区间 API 使用 `start_date/end_date`，结果采用 `requested_*` / `actual_*`、`initial_equity/final_equity/pnl`、`warmup_bars`。刷新保留用户所选日期；换股票按该股票实际范围重设；倒序与超范围由表单阻止。模拟盘请求不附带回测日期。
- 只修改 `frontend/trading.js` 和 `frontend/trading.css`；未改 index.html、app.js、ai.js 或后端。未重启正式服务、未访问正式数据、未运行 Git。

## 验证（2026-11-10，22:28 前完成）

```powershell
node --check frontend/trading.js
node --check scripts/phase6_ui_smoke.cjs
node scripts/phase6_ui_smoke.cjs
node scripts/phase5_ai_ui_smoke.cjs
```

- 全部最终退出码 0。Phase 6 探针 `passed=true`，浏览器 `errors=[]`；使用真实前端、真实本地 API 和真实引擎，行情与策略是明确人工测试夹具，模型回填部分使用显式 AI 响应替身。启动随机回环端口和独立 `.runtime/phase6-ui-*` 数据目录；测试服务由本脚本 stdin 指令正常退出。
- Phase 6 覆盖：32 项目录；7 预设；条件解释；JSON 错误不能确认/保存；重绘错误保留；负 offset 拒绝；真实条件组合保存与后端默认参数；所选股票实际日期默认值；切换股票/刷新保持规则；倒序禁止运行；真实指定区间研究回测；实际区间和资产/金额/收益率；保存历史重载；严格演示回测；已规范化条件 AI 回填及额外未支持条件拒绝；原模拟盘创建/单步且请求不含日期。
- 真实本地引擎的人工研究行情结果：请求与实际日期 **2024-02-13～2024-04-02**，预热 **30** 根，初始资产 **10,000.00**，结束资产 **10,743.74**，阶段盈亏 **743.74**，页面收益率 **7.44%**。这些是研究计价单位，不能当作真实市场或视频策略收益。
- Phase 5 AI 回归再次通过：`mountedFallback=false`、`statusReads=4`、`testCalls=2`，原设置、校正摘要、原文引用、旧 MA 映射及异步失效保护保留。
- 1440 / 390 / 320px 的条件编辑和结果页均无页面横向溢出。已目视检查移动端结果金额、条件编辑以及桌面指标目录截图。
- 首轮探针把后端补齐默认参数误判成对象差异，已修正测试为语义断言；没有为适配测试删除后端规范化参数。

报告和截图：

- [Phase 6 浏览器报告](../output/playwright/phase6-ui-result.json)
- [日期范围](../output/playwright/phase6-dates-1440.png)
- [指标目录](../output/playwright/phase6-indicators-1440.png)
- [桌面条件编辑](../output/playwright/phase6-conditions-1440.png)、[390px 条件编辑](../output/playwright/phase6-conditions-390.png)、[320px 条件编辑](../output/playwright/phase6-conditions-320.png)
- [桌面结果](../output/playwright/phase6-results-1440.png)、[390px 结果](../output/playwright/phase6-results-390.png)、[320px 结果](../output/playwright/phase6-results-320.png)
- [Phase 5 回归报告](../output/playwright/phase5-ai-result.json)

状态：本工作组实施与基本主流程自检完成，可交协调组织独立基本验收。没有运行对抗审计。真实供应商、真实视频完整自动映射与正式服务部署不在本组验证结论内；真实视频的盘中规则缺项以引擎工作组记录为准。
