# Phase 6 — 独立基本验收

日期：2026-11-10，Asia/Shanghai。工作目录：`C:/Users/Admin/Desktop/quant`，共享源码；无独立分支/worktree。协调聊天：`01a1c5d2-ffb5-7e31-958b-e559c07f63e1`。

## 结论：源码基本功能验收通过

引擎、UI、AI 工作组已收口；独立复验 **432 项 Python 测试通过、Node 测试 2/2 通过、真实本地 API/引擎的浏览器主流程通过**。本验收范围内无剩余必须修复项。接受的是下述固定源码快照与功能边界，不代表 GitHub 已发布或最终便携压缩包已完成迁移运行验收。

遵照用户要求，只检查需求、主流程及明显回归，不做对抗审计。本聊天仅写本记录及 `.runtime/phase6-review/` 内的隔离探针/证据；未修改产品源码、正式数据、Git 或 8765 服务，未新建聊天/子代理，未发送跨聊天消息。所有测试资源使用独立临时数据目录。

## 独立验证证据

- 全量 Python：`.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp .runtime/phase6-review/pytest-full-initial --tb=short`，**432 passed, 126 warnings in 46.09s，退出 0**。警告为 Backtrader 既有 `datetime.utcnow()` 弃用提示。[日志](../.runtime/phase6-review/pytest-full-initial.log)。本次实际只收集项目432项；为避免便携构建目录被后续递归收集，发布协调复跑时应明确使用 `pytest tests`。
- Node：`node --test tests/test_douyin_browser.cjs`，**2 passed / 0 failed，退出 0**。[日志](../.runtime/phase6-review/node-tests.log)。6 个前端 JS 的 `node --check` 均退出 0。
- 独立浏览器：以 `scripts/phase6_ui_smoke.cjs` 的隔离副本运行，变更仅为工作目录、测试数据与截图输出位置。**passed=true，errors=[]**；使用真实前端、真实 API/数据库及引擎，行情为明确人工夹具，仅 AI 回填响应使用替身。[报告](../.runtime/phase6-review/ui/phase6-ui-result.json)、[日志](../.runtime/phase6-review/ui-initial.log)。服务通过自己的 stdin 正常退出，未操作正式端口。
- 浏览器结果：研究日期 **2024-02-13～2024-04-02**，预热 **30** 根，初始资产 **10000.00**、结束资产 **10743.74**、阶段盈亏 **743.74**，展示收益率 **7.44%**。均为人工研究计价结果，不代表真实市场或视频策略收益。
- 已实际查看独立生成的 **320px 条件编辑、390px 结果、1440px 指标目录**截图；关键文字/金额可读。探针断言 1440/390/320px 均无页面横向溢出。
- 最终回归前快照 **22:30:18 +08:00**，回归后快照 **22:31:51 +08:00**；覆盖 `app/frontend/scripts/tests` 与依赖清单等 **110 个文件，前后完全相同**。[前快照](../.runtime/phase6-review/source-before.json)、[后快照](../.runtime/phase6-review/source-after.json)、[稳定性结果](../.runtime/phase6-review/source-stability.json)。不读取或哈希 `.env`、Key、正式数据库。
- **22:35:22 交接快照**发现协调继续修改 `scripts/build_portable.py` 并新增 `scripts/verify_portable.py`，核心 `app/frontend/tests` 与上述全量受检快照仍相同。新增内容为运行时 DLL、停止程序和迁移验证脚本，已阅读；实际构建/迁移仍待协调完成。此后快照不冒称全仓与回归时一致。[交接快照](../.runtime/phase6-review/source-handoff.json)。

## 需求接受检查

| 要求 | 检查结果 |
|---|---|
| 回测起止日期与区间盈亏 | 通过。无效/倒序/无行情区间拒绝；实际区间按可用日线报告。起日前行情只进入指标历史，不带入旧信号、持仓或资金；首日收盘信号次日开盘执行；期末未平仓按收盘市值计入盈亏。 |
| 指标无未来引用，回测与模拟共用 | 通过。32项注册指标有公式/参数/预热说明；所有指标前缀一致，负offset拒绝，未知值不误触发。回测、本地回放与Backtrader共用条件信号；本地两路径成交完全一致。 |
| 前端日期/盈亏/指标与旧流程 | 通过。股票覆盖默认日期、切换/刷新行为、倒序阻止、历史重载、严格回测、模拟盘创建/单步均覆盖。7个预设与高级JSON校验可用；错误草稿保留且不能确认/保存，重绘仍保持限制。 |
| AI 能力与未知缺项 | 通过。提示词读取同源能力/schema；未知指标、错误参数、遗漏条件、缺周期/仓位/卖出规则被阻止；证据逐字校验，原文保留。AI回填默认未确认，未确认组合不能运行。 |
| 独立日线确认版本可执行 | 通过。AI契约样例首板次日收盘确认，**第三日01-08开盘买入，01-09开盘卖出**；回测与本地回放一致，Backtrader同样两笔成交。示例期末9908.90元，不包装为策略有效性证据。 |
| 真实一进二视频边界 | 通过边界检查，**不接受“完整盘中策略已验证”的说法**。已核对引擎/AI对真实282段资料的记录，明确竞价/盘口/封板回封/题材筛选/动态分仓缺口。新增日线样例是独立定义，不是原视频替代。 |
| 自动路径、源码和包的数据排除 | 静态及配置测试通过；最终迁移/发布验收归协调，见下文。 |

### 真实视频的独立补充检查

在本地读取 AI 组保留的原始282段快照，先验证一个明确日线控制样例可接受，再把全部真实视频段落作为额外原文加入该控制输入。验证器返回 `rules=null`，分别指出盘中/竞价回封、题材/基本面、动态分仓/仓位上限三类缺口；传入原文和磁盘原始文件前后完全相同。[独立证据](../.runtime/phase6-review/actual-video-boundary.json)。这是“完整原文条件不可被日线提案掩盖”的验证实验，没有调用模型，没有声称完成真实视频提取或交易验证。

## 发现及关闭

首轮引擎仍在写代码时，`test_adjusted_prices_can_derive_prev_close_without_inventing_gap_data` 失败：研究行情缺 `prev_close` 时，预期 `[None,10,None,12]`，实际全为 `None`。影响为有连续历史但缺显式昨收字段的研究条件不能使用可推导昨收。已写初版报告并复核引擎修正：无缺口时由上一收盘推导，首根/明确行情缺口后保持未知；全量432项包含此用例及ATR缺口用例，现已通过，**关闭**。[首轮日志](../.runtime/phase6-review/pytest-engine-initial.log)。没有为通过测试修改预期或产品代码。

## 便携与发布边界

- 已读 `build_portable.py`、`portable_launch.py`、`PortableLauncher.cs`、`app/config.py`、媒体子进程与浏览器桥接实现。构建采用明确目录复制：Python/依赖、Node、Chromium、ASR模型、公共历史资源及应用代码；未复制 `.env`、正式资料库或用户媒体目录。
- 启动自动建立 `user-data`，设置包内ASR、Node和Chromium路径；媒体子进程使用当前 Python。`pythonw` 无 stdout/stderr 时重定向到包内 `user-data/server.log`，不存在必须手填运行时路径的设计步骤。配置测试证明内置模型会自动发现且显式模型路径仍兼容。
- `.gitignore` 排除 `.env`、`data/`、`.runtime/`、`output/`、`node_modules/`、`user-data/` 等；ZIP构建显式排除 `user-data`、`__pycache__` 和 `.log`。构建目录里现有测试 `user-data` 不等于将其打入ZIP。
- 已扫描177个源码/文档文本文件：常见Key/私钥格式无命中；源码候选目录没有数据库/用户音视频/Key文件；当前包在 `user-data` 外没有这些文件。真实全文夹具已移出 `tests/fixtures`，仅存在忽略的 `.runtime`。该检查是基本排除检查，不冒称全面秘密审计。[检查结果](../.runtime/phase6-review/source-release-check.json)。
- **协调仍需完成其已承担的发布工作**：最终源码刷新入包，新目录迁移启动、真实ASR模型加载及媒体子进程/内置浏览器验证，实际压缩包内容和SHA256、Git暂存候选、GitHub上传及远程确认。本验收未操作这些动作，不能据本报告声称它们已经完成；若最终产品源码再变更，应对相关部分复验并记录包对应源码哈希。

### 发布协调补充证据

已读取并复核协调提交的 [portable-verification.json](../output/portable-verification.json)：**passed=true、stop_exe_terminated_server=true**；包内 Python 依赖、pythonw无控制台启动、ASR模型CPU/int8实际加载、媒体worker的1秒WAV解析、32指标、300股203572行自动导入、Chromium 151启动及停止EXE均通过。这是复核协调运行证据，不冒称本验收聊天重复执行。协调说明沙箱限制曾阻止结束测试进程，使用已批准普通桌面权限复跑同一脚本通过。

协调新增 `pytest.ini` 限定 `testpaths=tests` 并排除构建/运行目录，已读配置，与本轮432项项目用例范围一致。实际ZIP正在生成；**最终解压到新目录复测、最终包/源码哈希和GitHub发布仍由协调完成**，其余不扩展检查。核心源码基本验收结论保持通过，无待修复项。

已阅读 Phase 5 最终验收与旁白修复交接，并在本轮全量回归中覆盖其测试。没有真实用户API Key，因此接受协议/替身控制流程，不承诺真实供应商连通、真实模型纠错质量或策略交易有效性。
