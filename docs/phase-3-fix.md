# Phase 3 必要修复：媒体批次截止时间测试

日期：2026-11-10（Asia/Shanghai）。状态：最小修复已完成，目标测试与该文件验证通过；Phase 3 全量回归和最终接受状态由基本验收线程统一记录。

## 范围与交接

- 协调线程：`01a1c47c-e4ff-7033-8038-f30d94df465e`。
- 基本验收线程：`01a1c488-0050-7012-a9d3-7914d4d009d5`。
- 工作目录：`C:/Users/Admin/Desktop/quant`；非 Git 目录，无 branch/worktree。
- 本修复仅修改 `tests/test_media_fetch_validation.py`，本报告供协调与基本验收读取。证据写入独立目录 `.runtime/phase3-media-fix-1tt8owvw/`。
- 未修改媒体产品脚本、trading/history、策略或订单；未写入正式 DATA_DIR；未创建聊天或代理，也未跨线程发送消息。
- 无本修复范围内的已知阻塞。未重复执行全量 pytest，最终全量检查由基本验收统一执行。

## 根因与复现

原测试仅为整批设置 `batch_timeout=0.03` 秒，使用真实 `time.sleep(0.05)` 模拟首项超时，并期望统计为 `attempted=1, failed=1, not_run=2`。但 `run_batch` 在调用 `environment()` 前就记录开始时间；环境信息收集、输入准备和依赖检查均计入批次预算。若前置工作超过 30ms，所有样本都应标为 `not_run/batch_timeout`，模拟 worker 根本不会被调用。

本线程独立运行原测试得到 **1 failed**，实际 `attempted=0, failed=0, not_run=3`，与既有 `.runtime/paper-evidence/full-pytest-final.log` 一致。进一步在未导入 paper 模块的独立进程中测得：

| 前置步骤 | 本次实测耗时 |
| --- | ---: |
| environment | 62.198ms |
| prepare_samples | 0.412ms |
| missing_dependencies | 2.009ms |

该进程 worker 调用次数为 0。既有诊断测得环境收集 214.762ms，本次虽然更快，仍超过 30ms。由此确认是测试对机器速度的隐含依赖，并非本阶段交易实现导致，也未发现需要更改媒体产品逻辑的功能缺陷。

## 修复内容与覆盖

新增测试内 `batch_clock` fixture，仅替换被测模块的 `time` 引用，不修改共享标准库 `time.monotonic`。时钟只在测试明确要求时推进；真实环境信息收集、输入规范化、批次计数与报告写入仍执行。截止时间用例固定依赖检查结果为空，使测试明确进入截止时间分支；缺失依赖的独立测试保持原样。

保留原测试名称及原有计数断言，以可控时钟推进 50ms 代替 sleep，预算仍为 30ms。增加对首项 `task_timeout` 转为 `batch_timeout`、每项 attempted/status/category、实际传给 worker 的剩余预算和每项耗时的断言。

覆盖共 4 个确定性场景：

1. 首项返回超时：1 次尝试、1 项失败、后续 2 项未运行，三项分类均为 batch_timeout。
2. 首项恰在截止时间返回成功：保留该项成功和媒体路径，后续 2 项未运行。
3. 环境收集恰好耗尽预算：0 次尝试、3 项未运行，不允许启动 worker。
4. 环境收集超过预算：0 次尝试、3 项未运行，不允许启动 worker。

这些断言能够发现后续样本仍被启动、成功结果被覆盖、批次超时错误分类、剩余预算传递错误，以及把零剩余预算误当成可执行预算等回归。未删除原有业务断言、放大 timeout 或添加 warning 过滤。其他针对真实子进程的测试及其等待保持原样。

## 先红后绿与有界验证

每次 pytest 均由 `subprocess.run(..., timeout=120)` 启动，使用唯一 basetemp 和隔离的 DATA_DIR、TMP、TEMP、TMPDIR；设置 `PYTHONDONTWRITEBYTECODE=1`，通过 `-p no:cacheprovider` 禁用共享 pytest 缓存。所有执行均在当前沙盒内完成，无需提权。

| 验证 | 结果 | pytest 用时 | 子进程退出码 |
| --- | --- | ---: | ---: |
| 原始 `test_batch_deadline_counts_remaining_samples` | 1 failed，复现预期断言失败 | 0.25s | 1 |
| 修复后该文件 `-k batch_deadline` | 4 passed, 36 deselected | 0.17s | 0 |
| 修复后完整 `tests/test_media_fetch_validation.py` | 40 passed | 8.08s | 0 |

命令公共部分为 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp <各次独立目录>`，分别追加原失败 nodeid、`tests/test_media_fetch_validation.py -k batch_deadline` 和 `tests/test_media_fetch_validation.py`。每条完整命令、绝对路径和返回码已记录在对应 JSON 中。

本次目标与文件验证没有报告 warning。既有全量日志中的 104 条 backtrader `datetime.utcnow()` 弃用 warning 未被过滤或修复，也不因本次文件验证通过而视为消失。此前全量结果为 173 passed / 1 failed；本报告不声称修复后的全量已通过。

## 可复核证据

全部位于 `.runtime/phase3-media-fix-1tt8owvw/`：

- `red.log` / `red.json`：修改前失败及完整运行参数。
- `diagnosis.json` / `phase1c-diagnosis/report.json`：独立耗时测量、未导入 paper、0 次 worker 调用和实际批次报告。
- `green-targeted.log` / `green-targeted.json`：4 个目标用例通过。
- `green-file.log` / `green-file.json`：整个文件 40 个用例通过。
- `test-change.diff`：本次测试文件变更。
- `validate_media_fetch.py.original`、`test_media_fetch_validation.py.original`：修改前快照。
- `scope-check.json`：与快照逐字节比对，确认媒体产品脚本未改动，并记录最终脚本和测试文件 SHA-256。

基本验收可直接读取此报告和证据，待数据工作完成后统一运行全量回归。由于新增 3 个参数展开后的用例，若其他工作未改变测试数量，原 174 个用例将增加到 177 个。
