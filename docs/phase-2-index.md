# Phase 2 可见工作组索引

开始日期：2026-11-09；最终接受：2026-11-10。工作目录/复用 checkout：C:/Users/Admin/Desktop/quant。非 Git，无 worktree、无 branch。

## 协调

Phase 2 - 策略组合、回测与模拟盘统筹：01a1c0d1-cfd5-71f0-9666-48c4fcc9bd54，host local。维护需求、契约边界、进度、验收和最终接受状态。

## 范围

见 phase-2-design.md 与 phase-2-plan.md。用户确认 A 股优先。策略筛选/组合属于本阶段；回测/模拟盘独立模块；本地 MVP。已读取原始附件、截图及主对话。主对话的流程主导授权继续有效。

## 工作线程

| 名称 | 线程 ID（host local） | 状态 | 检查点 |
|---|---|---|---|
| Phase 2 - 策略执行、回测与模拟账本实现 | 01a1c0dc-c83a-7d20-8e8f-15ed2e27a42a | 已完成并验收 | 稳定 API 契约、本地执行闭环；最终含修复145测试通过 |
| Phase 2 - 策略筛选与回测模拟盘界面实现 | 01a1c0dd-52ff-7c22-aed5-902e97cb9b8d | 已完成并验收 | 四模块真实 API 联调；320/390/1440浏览器验证通过，0脚本错误 |
| Phase 2 - 策略回测与模拟盘基本验收 | 01a1c0eb-083a-78b2-be6b-a7ba73fe2337 | 完成，其检查范围通过 | 独立131 pytest、9组补充业务检查、3组浏览器检查通过；协调补查的时钟问题另经修复复验关闭 |
| Phase 2 - 模拟盘启动时钟与验收问题修复 | 01a1c0fd-51ef-7233-ba87-9c533eb6e835 | 已修复并复验 | 14个时钟场景通过；全量145测试与两组Chrome回归通过；协调独立7场景通过 |

工作目录均为上述目录，无 branch。后端独占 app/ 与后端测试和 API 契约；前端独占 frontend/ 与浏览器主流程脚本；协调仅修改产品/README/阶段设计计划索引；验收只写 review 文档。后端和前端以契约同步。独立基本验收聊天已建立以准备检查矩阵，等待两个实现结束后才执行审查测试，避免并行写入影响验收。

## 检查点与阻塞

- 已完成：原始需求对照、现有结构核查、附件读取、市场选择。
- 已完成：实现、独立基本验收、时钟问题修复与针对性复验。原验收报告保留历史结论，时钟问题以修复报告与协调复验补充。
- 外部依赖：真实 AI 未配置；行情令牌/真实模拟券商账户未提供。可完成本地真实计算与接入口，外部账户联调不冒充已通过。
- 代码缺陷：盘中启动、暂停/重启恢复和晚到批量信号回填已修复；无剩余本地 MVP 代码阻塞。
- 最终接受：**本地 MVP 通过**。外部真实行情、券商、AI/ASR及云常驻不计入已完成能力。

## 最终交付与证据

- 资料 / 策略组合 / 回测 / 模拟盘四个独立工作区；手机 Dock、桌面侧栏、未保存校对保留、hash 深链。
- 多草案/手工策略、启用开关、等权或百分比权重、冲突处理与映射确认；回测/模拟使用冻结组合版本和独立账本。
- 首版限沪深主板普通股票、单标的日线、只做多，支持均线/阈值及收盘止损。真实CSV、演示、历史回放、盘后增量分别标记。
- 最终日志：`.runtime/phase2-fix-evidence/full-pytest.log`（145 passed in 22.10s）、`phase2-ui.log`、`legacy-ui.log`（均PASS、0浏览器错误）。独立基本验收另有9组业务检查与小屏五按钮几何检查，见 phase-2-review.md。
- 协调直接复跑：`.venv/Scripts/python.exe -m pytest tests/test_trading_clock.py -q -k 'first_observation or resume_after_open' --basetemp=.runtime/phase2-coordinator-clock-check -p no:cacheprovider`，7 passed、7 deselected，1.13s。
- 正式本地入口：[http://127.0.0.1:8765](http://127.0.0.1:8765)，隐藏启动PID 48440，标准 scripts/run.py、现有正式DATA_DIR。只读检查页面200、四模块存在、19条交易资源路径、必需接口无缺失；Tushare未配置、券商未连接。启动日志 `.runtime/phase2-server-20261110-000742.out.log` / `.err.log`。
- 报告：phase-2-design.md、phase-2-plan.md、phase-2-api.md、phase-2-backend.md、phase-2-frontend.md、phase-2-review.md、phase-2-coordination-findings.md、phase-2-fix.md。全部测试使用隔离数据，没有向正式工作空间灌入测试策略、行情或演示成交。
