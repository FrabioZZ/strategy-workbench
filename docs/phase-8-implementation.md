# Phase 8 实施记录

2026-11-11，quant/main，实施聊天 `01a1c89d-af69-7950-b4bd-fd82b4bd3d13`。实现和自测结果交协调聊天 `01a1c89a-52cc-7d60-8029-ee09c2d93417` 与基本验收聊天 `01a1c8a2-4fad-7c81-b9f0-d2094d3b60a9`。设计、接口来源和数据边界见 [phase-8-design.md](phase-8-design.md)。

## 使用方式

- 打开「运行配置 → 语音转写服务与金融词表」。本地 small 继续自动转写导入的音视频。选择 Qwen 时，填写对应地域的独立百炼 ASR Key，勾选上传与计费同意并保存。可选 Workspace ID 使用专属域名。选择本地并保存会移除该配置中的云 Key。
- 云模式下，上传文件或获取视频链接只缓存媒体。打开资料后点击「开始转写」，将首音轨转换成 PCM WAV 后上传，资料标题、默认主题及热词也会随转写请求发送。3.1 按 Token 计费，以百炼账单为准。临时 OSS 仅用于本机低并发用途，文件有效期 48 小时。保存配置不验证连接。
- 遇到超时或服务重启，从资料页重试。已取得远端任务编号时继续查询，避免重新提交。远端明确失败后，重试可能重新提交并计费。提交结果不明时先核对百炼控制台。仍有未确认任务时，改过主题或地域需恢复原配置才能继续查询。
- 历史资料可点击「创建副本重新转写」。副本复用缓存并保留父资料入口，转写后得到独立原文及时间戳。原资料的策略、证据和校对记录保持原样。策略 JSON 含识别元数据、原始识别段落及父来源 ID。

## 自测证据

| 检查 | 结果 |
|---|---|
| `.venv/Scripts/python -m pytest -q --basetemp .test-tmp/p8-final-regression -o faulthandler_timeout=45` | 452 通过。126 条既有 backtrader `utcnow` 弃用提示。初次受限沙箱在 Windows 回环套接字创建处阻塞，本机权限重跑成功。 |
| `tests/test_qwen_asr.py` | Windows DPAPI、独立密钥与同意、官方 HTTP 合同、句级毫秒转换、已完成结果复用、超时续查、配置变化防止重提、PyAV PCM、正常入口重试与历史证据保持。远端使用 HTTP mock。 |
| `node --test tests/test_transcription_ui.cjs` | 1 通过，覆盖自动转写、缓存重试、刷新、校对和证据定位。 |
| 本机 Chrome 与普通启动 | `scripts/run.py` 启动成功，390px 视口无横向溢出，实测设置面板拒绝未同意的云配置并保存本地设置。 |
| portable 启动 | 隔离目录运行 `scripts/portable_launch.py --no-browser`，模型发现标记验证随包模型自动选择，`/api/status` 正常。此项验证启动入口及路径，未重建发布 ZIP。 |
| 实际本地 small | 授权样本的前 24 秒经普通上传入口、本地队列和真实 faster-whisper-small 生成 4 个时间段。原始识别与当前转写一致，结果只写到隔离测试目录。此项验证执行兼容性，未人工计分。 |
| 静态检查 | `node --check` 检查两个变更脚本，`git diff --check` 无空白错误。 |

本机加载环境中没有明确 ASR/Qwen/DashScope 凭据，也没有 `data/asr-config.json`。本阶段实际云连接、服务计费和 small/Qwen 识别准确率待专用 Key 与同段人工对照。合同 mock、启动烟测和本地模型验证分别保留，未进行付费调用。

实施仅修改 ASR 适配器、配置、队列、资料存储、配置/资料 UI 与阶段文件。既有 `app/ai/client.py`、`docs/phase-5-index.md`、`tests/test_ai_client.py` 保持交接时状态。

实施状态：可交独立基本验收。发布 ZIP、实际云连接和识别质量对照未验证。
