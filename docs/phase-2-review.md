# Phase 2 独立基本验收

日期：2026-11-09（Asia/Shanghai）。验收聊天 `01a1c0eb-083a-78b2-be6b-a7ba73fe2337`；协调聊天 `01a1c0d1-cfd5-71f0-9666-48c4fcc9bd54`。目录 `C:/Users/Admin/Desktop/quant`，非 Git，无 branch/worktree。

## 结论

**本地 MVP 基本验收通过，未发现必须修复的产品问题。** 独立运行现有 **131 项 pytest 全部通过**，另有 **9 组独立业务检查通过**；一期资料/媒体、二期交易主流程及补充草案/小屏浏览器检查均通过，最终浏览器错误为 0。结论同时依据业务复算、代码检查与浏览器行为，不仅依据测试数量。

可交协调接收本地成果并更新最终接受状态。真实 AI/ASR、Tushare 权限与行情、券商连接仍为**外部待联调**；本结论不覆盖这些能力，也不表示云端常驻服务已完成。依据 phase-2-design.md、phase-2-plan.md、phase-2-api.md 及协调补充要求，只做需求对齐、主要流程与明显回归检查，**未做对抗审计**。

没有修改产品代码、原测试或其他实现线程文件，没有启动新聊天/后台代理，没有发送跨线程消息。交付文档仅本报告；自身测试快照、脚本、日志、隔离数据库和截图位于 `.runtime/phase2-review-evidence/`，未使用正式 `data/` 或用户运行服务。

## 实现完成门槛与隔离

先准备检查矩阵，再通过 wait_threads 连续有界等待，每次 50 秒，后续带 afterCursor。确认前端 `01a1c0dd-52ff-7c22-aed5-902e97cb9b8d`、后端 `01a1c0dc-c83a-7d20-8e8f-15ed2e27a42a` 均为 completed 后才读取最终产品实现并测试。后端最终完成时间为北京时间 23:41:23。

测试从完成后的源码快照运行，复制 app/frontend/tests/scripts/deploy 及打包测试所需文档/依赖清单，不复制 .env、正式数据或个人配置。45 个原始代码/测试/浏览器脚本的 SHA256 记录于 `source-sha256.json`，复验后核对 0 个变化。浏览器复跑脚本仅为快照指定现有 Python 路径，没有修改所测产品代码。

实现报告已明确 Windows 沙盒 TestClient 阻塞，本轮采用获批的沙盒外本地隔离测试。每次 pytest 限时 45/60 秒，浏览器和子服务限时 60 秒；浏览器使用现有 Chrome，无下载浏览器、模型或外部账户操作。测试端口 8892/8893/8894 启动前检查空闲，结束关闭自己的服务。

## 需求检查矩阵

| 检查项 | 结果 | 本次证据 |
|---|---|---|
| 手机 Dock、桌面侧栏四模块真实切换 | 通过 | 二期 smoke 在 320/390/1440px 检查独立面板可见性、hash、刷新深链、键盘跳转；非当前面板隐藏 |
| 小屏主按钮与安全空间 | 通过（浏览器范围） | 独立 320×568 几何检查：保存组合、运行回测、创建/启动/同步模拟五个按钮均可命中，完整位于 Dock 上方；Dock 高 69px，底部留白 77px，无横向溢出。CSS 同时使用 env(safe-area-inset-bottom) |
| 切换保留未保存转写 | 通过 | 输入未保存校对，往返组合/资料后内容一致，随后保存成功；资料 DOM 保留 |
| 既有资料与媒体 | 通过 | 一期 smoke 实际播放本地 WAV/视频、历史证据跳转、未知媒体下载回退；校对、提取、引用、导出、过期与持久化通过 |
| 从已有草案建立组合，保留证据 | 通过 | 独立浏览器用经 validate_strategy 校验的完整草案完成选择、阈值/止损映射、确认和保存；API 对照 source_id、transcript 和引用。更改参数会取消确认 |
| 未确认、缺规则/说明、全禁用不能运行 | 通过 | 补充逐一断言 readiness=false，回测/模拟创建 409；现有测试覆盖权重不足和缺失止损映射 |
| 同资料新草案、转写变更使旧组合过期 | 通过 | 同资料同转写版本再生成草案，旧组合不就绪，回测/模拟启动 409；现有测试覆盖转写编辑。原 run 内容逐字段不变 |
| 开关、权重实际影响运算 | 通过 | 相同数据，两项策略权重 25/75、75/25、第二项禁用时，回测和回放首笔分别买 200、700、900 股；禁用项有效权重 0。现有测试另证等权及目标冲突阻止成交 |
| 指定版本/数据与旧账本冻结 | 通过 | 回测保存组合快照、证据、数据 ID/hash、费用；模拟保存冻结组合。编辑组合不改旧快照；运行中继续用冻结版本，暂停后按旧版本重新启动拒绝，需建新会话 |
| 下一根开盘、预热不偷看未来 | 通过 | 01-05 信号在 01-06 开盘买入；MA slow=3 前两根目标 0、第三根产信号、第四根首次成交。增量首次同步只预热，首次观察日及以前补齐数据不补成交 |
| 费用、现金、持仓、净值复算 | 通过 | 10000 元，10 元买 900 股费用 5；12 元卖 900 股费用 10.40；最终现金 11784.60、总费用 15.40、空仓。重复回测成交/净值一致 |
| 初始资金计入最大回撤 | 通过 | 增量预热无净值点；首笔 10 元买 900 股、费用 5，收盘 9.5：现金 995、净值 9545、收益 -4.55%、最大回撤 4.55%。engine.py:106 从 initial_cash 建峰值基准 |
| 整手、现金、T+1、停牌/零量、限价 | 通过 | 现有测试覆盖整手/现金、四舍五入费用、当日不可卖/次日可卖、开盘限价拒单；补充 suspended=1 和 volume=0 均无成交且有原因。代码对滑点越界、超日成交量保守拒单 |
| CSV 日期、代码、限价/价格、不支持数据 | 通过 | 拒绝未来/周末、乱序/重复、缺限价、非主板、异常限价、越界 OHLC、昨收不连续、复权、缺证券/公司行为确认。停牌需有效可验证价格，零价/空价不被当作可成交数据 |
| CSV 单标的过滤 | 通过 | 同 CSV 含 000001.SZ/600000.SH，分别运行只消费所选标的，信号数正确，另一标的不混入；不存在标的返回 400。运行日期范围为所选数据集全区间 |
| 各账本独立 | 通过 | 新模拟账户现金等于初始资金、空仓空成交；回测不灌入模拟。新账户同步数据选择不继承前账户 |
| 回放/增量区分，无行情不造假 | 通过 | 页面标注历史回放或盘后新行情、本地撮合；回放不可改数据。空行情增量同步后 0 成交、100000 元不变，等待状态明确 |
| 重复请求/行情幂等，重复 ID 返回当前状态 | 通过 | step 重复不推进；增量完成后重放早先 warm ID 返回当前完整会话，而非旧响应；同数据新 ID 不增成交；同 ID 换操作/数据返回 409 |
| 过期、乱序、修订、失败输入保护 | 通过 | 过期为 stale、游标不动、0 成交，其 ID 改指其他数据返回 409；旧数据不倒退/不增成交；修改已消费行 409，事务回滚后会话逐字段不变 |
| 启停、重启暂停、持久化 | 通过 | 独立复跑测试验证启动、暂停、后台 tick、重启 paused，游标/成交保留；请求指纹随 SQLite 账本持久化 |
| 外部状态与真实联调 | 外部待联调 | capabilities 的 broker.connected=false、Tushare verified=false；页面说明未接券商与配置状态。未使用真实行情/模型凭证，不能记为外部成功 |

## 独立执行记录

以下路径均相对 `C:/Users/Admin/Desktop/quant/.runtime/phase2-review-evidence/`。命令由隐藏子进程运行并设置硬超时，退出码另存。

### pytest

在 snapshot/ 中运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/Admin/Desktop/quant/.venv/Scripts/python.exe' -B -m pytest -q --basetemp=C:/Users/Admin/Desktop/quant/.runtime/phase2-review-evidence/pytest-tmp -p no:cacheprovider
```

**131 passed in 19.84s，退出 0**。日志 `pytest.log`、`pytest.err`，退出码 `pytest-exit.txt`。包含既有 115 项及交易 16 项。

独立业务补充脚本 `snapshot/tests/review_checks.py`：

```powershell
& 'C:/Users/Admin/Desktop/quant/.venv/Scripts/python.exe' -B -m pytest -q tests/review_checks.py --basetemp=C:/Users/Admin/Desktop/quant/.runtime/phase2-review-evidence/extra-tmp -p no:cacheprovider
```

**9 passed in 1.78s，退出 0**。日志 `extra.log`、`extra.err`，退出码 `extra-exit.txt`。覆盖新草案、权重/禁用对两种账本的影响、禁止启动、首笔回撤、MA 缺历史、重复 ID 当前状态、旧行情修订、过期请求和 CSV 边界。

### Chrome / Playwright

NODE_PATH 为 `C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`，Node 使用同 runtime 的 `dependencies/node/bin/node.exe`，浏览器 channel=chrome。在 snapshot/ 中运行：

| 脚本与端口 | 结果 | 日志 |
|---|---|---|
| scripts/review_phase1_ui.cjs，8893 | 一期资料/媒体回归通过，0 page errors | phase1-ui.log / phase1-ui-exit.txt=0 |
| scripts/review_phase2_ui.cjs，8892 | 四模块、权重/CSV/演示/回测/模拟通过，0 browser errors | phase2-ui.log / phase2-ui-exit.txt=0 |
| scripts/review_source_ui.cjs，8894 | 完整草案映射/确认/证据，小屏五个主按钮，等待账户通过，0 errors | source-ui.log / source-ui-exit.txt=0 |

前两个脚本是原 smoke 的快照，仅将 Python 路径指向现有虚拟环境，数据/输出仍在自己的 snapshot 下。二期真实计算为两笔成交、费用 118.12 元；空行情增量账户零成交。交易 API、SQLite 和计算器均真实运行；一期下载/ASR/AI 使用明确测试替身。有效本地 WAV/视频的探测与 Chrome 播放实际发生。

独立草案检查首次用旧 FakeExtractor 时未就绪（退出 1）：该替身只有 buy 规则、缺其他类别/标的/周期，真实校验器产生未解决问题，后端正确拒绝。没有修改产品放开限制；保留 `source-ui-incomplete-fixture.err`、对应退出码及 `snapshot/.runtime/source-review/` 数据库。随后 `tests/review_ui_server.py` 提供完整 buy/sell/position/stop_loss、标的/周期引用，仍通过产品 validate_strategy 校验，成功路径复跑通过。测试夹具调整不代表真实模型已验证。

截图和机器结果位于 `snapshot/output/playwright/`：

- `phase2-result.json`、`phase2-mobile-{portfolio,backtest,paper}.png` 及对应桌面截图；本轮实际查看桌面组合、手机回测/模拟盘。
- `independent/source-and-geometry.json` 记录五按钮几何/命中/溢出；`320-backtest-action.png`、`320-paper-action.png` 已实际查看，主按钮可见；`320-source-confirmation.png` 保留参数修改后的状态。
- 一期 `phase1b-fix-result.json` 记录实际媒体播放时间、历史证据与缓存保留。

## 能力与验证边界

- 仅沪深主板普通股票、单标的、日线、只做多。无 ST/上市初期/其他板块、公司行为、复权价撮合、盘口排队、盘中止损、完整交易日历/财报 PIT/历史税费表；CSV 真实性与证券属性由用户核实。
- 均线/价格阈值及日线收盘止损须明确参数、保留证据并人工确认；缺项/问题阻止运行。未支持规则不能勾选后强行运行，也不证明任意自然语言与映射自动等价。
- 增量为盘后本地模拟，首次历史数据预热，服务运行时轮询，退出服务不继续跟盘。自然日 freshness 与北京时间 18:00 完成日线判断是简化，不等同精确交易所日历。
- 回测使用数据集全区间。日期合法性/排序及单标的过滤已验证，未提供独立起止日期控件；需要不同区间应导入相应不可变数据集。
- 真实 Tushare 令牌/权限、券商、真实 ASR/AI 未验证。适配器存在或配置标志不代表外部成功；历史回放及演示持续标注。
- 小屏证据来自本机 Chrome 视口、DOM 几何、截图及 safe-area CSS 检查；未实测 iOS 刘海设备、软键盘或所有移动浏览器。

## 交回协调

**基本验收完成，无必须修复项；建议接收本地 MVP，保留外部待联调及上述限制。** 协调负责更新阶段索引、PRODUCT/README 与最终接受状态。本验收未自行宣布外部能力完成，也未安排额外审计或后续阶段。
