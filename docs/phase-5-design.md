# Phase 5 — 简化转写、本机 AI 与可执行策略

日期：2026-11-10，Asia/Shanghai。用户已明确授权同步实施；本文件记录执行边界，不增加开工审批。补充要求：AI 检验语音识别的语言合理性、主动修正并按内容自动命名策略。

## 目标与选择

沿用本机 FastAPI / SQLite / 原生网页。分享链接导入后自动获取媒体并转写；默认无播放器、无全文，处理中展示不伪造百分比的进度条及“识别中，请保持程序打开并保持设备唤醒”，成功展示勾选和“转写完成”。原文校对入口按需展开，以保留修错和证据定位能力。失败、缓存重试、缺 ASR 模型不能显示成功。

AI 基础已有摘录 adapter、严格原文引用、任务队列和草案；尚无用户可配置凭据、语义校正及 AI 执行参数映射。选择本机后端直连用户选择的模型 API；凭据用 Windows DPAPI 加密保存，仅本机回环客户端可操作凭据接口，不进产品云端、不返回浏览器、不进入日志/导出。调用供应商时必须向该供应商发送认证凭据和待处理内容，界面如实说明。非 Windows 无安全储存方案时明确失败，不能悄悄明文落盘。

先支持一组经过官方文档核实的 OpenAI 兼容 API 预设和自定义兼容接口；选择模型也可手输 model ID。不要冒称未经实现的原生协议可用。已有 Ollama/测试注入需要兼容。保存不等于已连通，提供实际轻量连接测试。供应商/URL 改变不得默用旧 Key。禁止自动携凭据跟随重定向。

提取时先 AI 校正明显错词/断句，再摘录、命名。保留原始转写及改动记录；校正不能补造交易条件，涉及数字、否定、买卖方向、比较关系等不确定语义时保留原文并加入待确认问题。可信证据必须指向明确的原始或校正版本，不能把修正后的引文冒称未修改原话。前端默认仅显示校正摘要，按需展开改动，原始全文不默认出现。

实际输入参考：用户最新资料《一进二 #龙头主升战法 #打板》共282段，包含“本質是在和油脂比認知,衡量化拼速度”“如果你今天打手把,明天追二把”等识别文本。上下文可能对应“游资”“和量化”“首板/二板”，这类术语修正应有原文记录；不能仅因语言不顺就改交易含义。该资料打板逻辑超出现有DSL，不能强行映射。用户已明确选择“先完成本次接入；打板单独做下一阶段”，本阶段不扩建打板引擎。

AI 映射仅输出既有引擎能执行的 ma / threshold 结构；核实日线、买卖语义、目标仓位、可选止损、原文证据。不能将价格突破单均线误转成双均线，不能遗漏筛选条件。缺参数/有疑问/不支持内容返回问题并禁止就绪。AI 建议回填组合，confirmed=false，经用户确认保存后沿用既有组合版本与 readiness，供回测和模拟盘共享。无任意 Python/JS 代码执行、无真实下单。

## 并行文件边界

1. 转写体验：frontend/app.js、index.html、style.css，app/jobs.py 的 download 分支与自动 ASR 衔接，相关转写测试。保留 config 的 AI UI 挂载点。app.js 提供 document-rendered 事件供 AI 摘要扩展。不得改 extract 分支。
2. AI 后端：新 app/ai/ 模块、app/adapters/extractor.py、app/main.py、app/config.py、app/store.py、app/jobs.py 的 extract 分支，app/trading/portfolios.py 的候选命名与必要验证；相关新测试。不得改 download 分支及前端。
3. AI 前端：新 frontend/ai.js、ai.css、frontend/trading.js，相关 UI 探针。不得改 app.js/index.html/style.css；协调负责静态文件挂载及共享接口整合。
4. 协调：本阶段索引/设计/契约、集成测试、共享改动、正式本地服务备份重启。基本验收单独可见聊天，发现问题用同阶段可见修复聊天。

## AI HTTP 契约

- GET /api/ai/config → {providers:[{id,label,base_url,models:[string]}],provider,base_url,model,has_api_key,configured,storage_note}；不得包含 key。
- PUT /api/ai/config ← {provider,base_url,model,api_key?}；返回同上。空 key 仅同供应商/地址保留，变化必须重新填写；DELETE /api/ai/config 删除用户配置并明确当前状态。
- POST /api/ai/test（无 body）→ {ok:boolean,message:string}；使用已保存配置真实请求，不保存返回内容。
- /api/status 兼容原字段，ai_configured/provider/model/note 从当前有效用户配置取得。
- POST /api/ai/strategies/{source_id}/mapping（无 body）→ {source_id,source_revision,rules:object|null,mapping_note:string,questions:[string],evidence:[{field,segment_id,quote}],ready:boolean,provider,model}。source_id 为 /api/trading/strategies 返回的草案 id。ready 是建议完整性，不替代用户确认。
- 原 /api/documents/{id}/extract 保持排队入口，自动做校正、命名、摘录。GET document 增补 ai_review（null 或 {status,summary,changes:[{segment_id,original,corrected,reason}],questions:[string]}）。保留原始转写；具体原始/校正快照设计由后端实现并记录。
- 候选 title 使用模型生成 strategy.title，保留资料标题作为 source_title。
- 前端接收 document-rendered 事件，event.detail 为完整 document；AI 设置保存/删除后调用现有 refreshConfig()。

## 验收

覆盖成功/失败/重试/刷新、无视频与默认无全文；桌面和手机布局；本机密钥写入/重启/删除/接口脱敏/目的地变化；协议请求和非JSON/超时失败；校正原文保全、歧义阻止、命名；完整 AI 输出→组合→回测与模拟回放的接口集成。使用替身的测试明确标注；用户未提供 Key 时不能宣称真实供应商连通或真实模型质量已验证。外部平台和 ASR 采用可获得的真实样本测简化流程。基本复核，不运行对抗审计。
