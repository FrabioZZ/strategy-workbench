# Phase 8 Implementation Plan

目标：独立且可恢复的 Qwen 文件转写，与本地 small 并存。架构见 phase-8-design.md。Python/FastAPI/httpx/PyAV，原生 JS。

按现有授权在本聊天自行实施；不新 worktree、不提交、不推送，保留指定既有改动。协调另开基本验收聊天。

## 任务与验证

- [x] 配置合同：新增 app/asr/configuration.py、tests/test_qwen_asr.py，验证默认本地、显式上传同意、独立 DPAPI、换地域不复用 Key、公开响应不泄密。
- [x] 云适配器：新增 app/adapters/qwen_asr.py。HTTP mock 验证上传、异步字段、热词上下文、时间戳、结果缓存和超时续查。PyAV WAV 抽取不新增有损编码。
- [x] 队列与数据：正常转写/重试走动态配置，云模式需手动发起，原始记录保留，历史副本带父关系。
- [x] UI：配置服务、模型、地域、独立 Key 和同意，显示主题与副本入口及识别元数据。
- [x] 回归：452 项 Python 测试、1 项 Chrome 转写回归，普通和 portable 启动及配置浏览器烟测。见 [实施记录](phase-8-implementation.md)。
- [ ] 真实 small/Qwen 同段质量对照，待 ASR 专用 Key。

## 重点复核

无Key不发送网络请求；云失败无静默回退；已提交任务不因重启再次付费提交；历史证据不被覆盖；portable模型自动发现及离线转写保持兼容。mock不构成真实质量证明。
