# Phase 8 设计：Qwen 文件转写

2026-11-11，quant/main，实施聊天 01a1c89d-af69-7950-b4bd-fd82b4bd3d13。

## 官方合同

- [新版专用 HTTP API](https://help.aliyun.com/zh/model-studio/qwen-audio-asr-filetrans-http-api)：qwen-audio-3.1-asr-flash-filetrans，POST /api/v1/services/audio/asr/transcription；Bearer ASR Key、X-DashScope-Async: enable；input.file_urls 单元素数组；input.context user/input_text；parameters 必须存在，vocabulary 为词到整数权重。句级 begin_time/end_time 为毫秒。
- [模型概览](https://help.aliyun.com/zh/model-studio/asr-model) 与 [模型说明](https://help.aliyun.com/zh/model-studio/qwen-audio-3-1-asr-flash-filetrans)：北京和新加坡，3.1 按 Token 计费，不硬编码价格。
- [上传临时文件](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)：GET /api/v1/uploads?action=getPolicy&model=模型，multipart OSS 表单；同账号同模型绑定，48 小时；提交带 X-DashScope-OssResourceResolve: enable。该机制官方不推荐生产/高并发，本阶段仅用于本机低并发工具，须在 UI 说明。
- 旧 qwen-asr-api-reference 仍描述 qwen3 的 file_url 合同；fun-asr 页现已拆分。实现只采用新版专用页，不混用旧参数。允许旧 DashScope 地域域名（官方标明迁移来源），可填 Workspace ID 使用推荐专属域名。

## 架构与数据

新增 app/asr/configuration.py 复用 DPAPI，单独 asr-config.json；默认 local，明确保存 cloud_enabled 才可调用。不会读取 AI_API_KEY、DASHSCOPE_API_KEY 或 ai-config。模型限定已核实 3.1，地域北京/新加坡。金融词表默认权重4，资料标题与主题组成最多400字符上下文；small 使用 initial_prompt/hotwords。上下文仅辅助识别，不替换数字或原文。

新增 app/adapters/qwen_asr.py，worker 内读取 DPAPI 配置；主进程不把 Key 写入任务请求。PyAV 首音轨提取 16kHz mono PCM WAV，限制时长；临时文件退出清理。提交后立即保存远端 task_id 和配置指纹，失败/重启后重试只查询原任务；明确终态失败才允许下一次重提，提交网络结果不明时阻止自动重复计费。结果本地缓存和原始识别 JSON 保留，URL/Key 不进入公开错误。

沿用 Jobs 单队列、recover、中断/超时和正常重试入口。云任务由用户点击开始转写（下载和上传不自动触发云调用）。配置修改立即生效。本地保留自动接续。

documents 增加 parent_document_id、asr_metadata、original_segments。重转写创建共享缓存的独立副本（父资料ID），原资料及策略、校对审计不变。原始识别与时间戳单独保留，编辑仅更改当前稿。配置和资料界面显示供应商/模型、联网/上传/计费条件及历史来源。

## 验收边界

mock 合同、DPAPI、缓存重试、启动恢复、无凭据本地回归及启动烟测。本阶段不真实调用云端、不声称准确率提升。真实质量需用户授权中文金融同段样本、独立地域 Key、小模型与 Qwen 人工对照。
