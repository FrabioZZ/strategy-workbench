# Phase 5 — 普通视频旁白映射修复

日期：2026-11-10（Asia/Shanghai）。工作目录：`C:/Users/Admin/Desktop/quant`，非 Git；branch/worktree 不适用。本聊天为同阶段可见跟进修复，范围为普通视频资料 → 既有日线策略映射，打板及扩展 DSL 属下一阶段。

## 问题与修复

协调复现：对 `tests/test_ai_backend.py` 的标准有效策略追加 `s4=大家好，今天和大家分享这个方法，感谢观看。` 后，`validate_proposal` 返回 `rules=None`。根因是全文覆盖检查要求所有子句都匹配交易规则，连不承载交易条件的旁白也视为遗漏条件。

- 新增 `app/ai/mapping_language.py`，以完整子句正向匹配明确的非规则叙述：问候、节目介绍、方法讲解过渡、例子/图表说明、基础趋势说明、结束语和观众互动。使用受限词组组合，不接受任意主题或通配后缀，不依赖“没看到关键词就放行”。
- `app/ai/mapping.py` 的全文、摘录规则及字段引用可包含上述旁白；旁白不贡献参数覆盖，单独引用旁白不能证明价格、仓位等字段。真实交易子句仍须逐项匹配现有规则与数值。
- 保留子句换行边界，识别中文/英文感叹号；不拆小数点或问号，不改比较运算、买卖方向、数值及执行时点。未做交易语义规范化或扩大引擎含义。
- 原转写、校正快照、引用全文和 `transcript_version` 均原样保留，无需删掉真实转写中的开场/结尾。
- 未识别句子仍返回所在段落的待确认问题；遗漏 ROE、任意指标百分比、时间/周期、否定、额外买卖限制及不明“灵活操作”仍阻止映射。不会把所有未覆盖句子放行。

这是小范围确定性语句分类，不是通用自然语言解析器；未覆盖的自由措辞仍可能需要确认。真实供应商调用、模型质量与真实视频质量不由这些夹具测试证明。

## 测试与基本复核

先新增 `tests/test_ai_mapping_narration.py`，在未改生产代码时实际运行：**12 failed / 14 passed**。失败均为应接受的普通旁白及带旁白引用场景，条件保护测试原本通过。

修改后执行：

```powershell
$mappingTemp = Join-Path (Get-Location) ('.runtime/mapping-tests-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ai_mapping_narration.py tests/test_ai_backend.py -q -p no:cacheprovider --basetemp $mappingTemp --tb=short
```

结果：**64 passed**（本次新增26项 + 当时后端测试38项）。包括 threshold、双均线、原始/校正版本引用保全、遗漏交易条件拒绝，以及既有 AI → 人工确认组合 → 回测/模拟回放契约。测试不调用真实模型。

首轮默认 pytest 缓存/临时目录有 Windows 权限问题；指定工作区内唯一 `.runtime` 目录、关闭 pytest 缓存后上述回归正常完成，没有为此修改产品。

按相同隔离方式执行全仓库 `python -X utf8 -m pytest -q -p no:cacheprovider --basetemp <独立.runtime目录> --tb=short`：**381 passed / 9 failed / 104 warnings**。警告为 Backtrader 的 `datetime.utcnow()` 弃用提示；9个失败全部位于当时的 `tests/test_phase6_engine.py`，需要下一阶段的 conditional DSL、日期区间契约及 `app.trading.indicators` 模块：

- `test_capabilities_publish_actual_rule_schema`
- `test_conditional_rules_accepted_and_invalid_params_rejected`
- `test_interval_does_not_trade_warmup_or_include_earlier_equity`
- `test_interval_validation[changes3-400]`
- `test_interval_validation[changes4-400]`
- `test_formula_values_and_prefix_invariance`
- `test_cross_boolean_unknown_and_offset`
- `test_first_board_requires_known_prior_and_actual_limit`
- `test_confirmed_daily_first_board_rule_shared_with_paper`

本组未修改上述测试或其业务范围，不宣称整仓全绿。基本自查确认仅本次四个交付文件发生本组编辑：`app/ai/mapping.py`、`app/ai/mapping_language.py`、`tests/test_ai_mapping_narration.py`、本记录。未改其他组文件、正式数据、`.env`、Key 或 8765 服务；未新建聊天/代理或向其他聊天发消息。

状态：修复及本组验证完成，交由阶段基本验收聊天读取最终文件复核。未运行对抗审计。
