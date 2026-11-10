# Phase 1 补充验证：平台导入与语音转写

验证日期：2026-11-10，Asia/Shanghai。本轮范围仅为用户要求的三项实际能力验证。复用当前可见聊天记录协调、验证与结论；未开始新的实现阶段或对抗审计。工作目录为 `C:/Users/Admin/Desktop/quant`，非 Git 仓库，无分支、无独立 worktree。

## 本轮结论

**三项均未达到当前环境下的真实成功标准。** 两个平台链接可提交，但本次都没有取得媒体；有效媒体可导入，但没有运行语音识别并生成文本。不能用历史成功或测试替身判定本轮通过。

| 验证项 | 实际结果 | 阻塞点 / 接收状态 |
| --- | --- | --- |
| Bilibili 链接导入 | `BV1bK411W797?p=2` 提交返回 HTTP 202；下载任务 failed，`has_media=false` | 当前域名解析到 `198.18.1.81`，被下载器非公网地址检查阻止；未通过 |
| 抖音链接导入 | 用户此前提供的 `https://v.douyin.com/aU0BxZKBvVI/` 提交返回 HTTP 202；下载任务 failed，`has_media=false` | 当前短链域名解析到 `198.18.0.87`，同样被拦截；未通过 |
| 导入媒体的语音转文本 | 真实缓存音轨上传返回 HTTP 202；媒体读取 HTTP 200；手动转写返回 HTTP 409，段落数 0 | 正式服务和隔离验证配置均为 `asr_configured=false`；缺少模型配置，未通过 |

## 实测方法与证据

1. 使用生产 `create_app`、真实 API 路由、任务调度和媒体子进程；无下载器、ASR 或 AI 替身。仅将测试资料库指向独立 `.runtime` 目录，媒体任务超时设为180秒，其余大小/时长限制沿用200 MB / 120分钟。没有调用策略提取。
2. 两条链接先在受限环境运行一次，再在获准的宿主执行环境复跑一次，结果相同。宿主报告为 [平台验证报告](../.runtime/phase1-supplement-20261110-200122/report.json)；首次报告保留在 `.runtime/phase1-supplement-20261110-200052/report.json`。验收探针 [phase1-supplement-verify.py](../.runtime/phase1-supplement-verify.py) 的退出0仅表示探测完成，不表示三个能力通过。
3. 对 B站直接调用同一底层 `_download` 进行诊断，异常发生在 `validate_url → public_address`，消息为“不允许访问内网、保留或本机地址”，尚未进入 yt-dlp 页面提取。脱敏诊断见 [diagnostic.json](../.runtime/phase1-supplement-diagnostic.json)。系统DNS查询的三个域名均返回非公网地址：B站 `198.18.1.81`、抖音短链 `198.18.0.87`、抖音主站 `198.18.0.127`。见 [DNS证据](../.runtime/phase1-supplement-dns.json)。本轮没有识别或修改造成该解析的系统软件，不能据此断言某个特定代理客户端是根因。
4. 为独立验证转写入口，复用2026-11-09真实获取的B站 M4A 音轨，走本地上传接口。该文件为2,170,299字节、97.941111秒、有音轨无视频，PyAV完整解码4218个音频帧。SHA256：`c28a3156367a622c9ebd377842b7815f23332526f1d5e7bd9edad898209c4e6e`。转写入口明确拒绝，缓存保留，没有生成转写任务或文本。见 [ASR独立验证报告](../.runtime/phase1-supplement-asr-20261110-200317/report.json) 和 [探针脚本](../.runtime/phase1-supplement-asr.py)。这不是本轮平台下载成功证据，也不是完整视频画面导入证据。
5. 环境可导入 faster-whisper 1.2.1、CTranslate2 4.8.5、PyAV 19.0.2；已安装识别依赖不等于已准备模型。正式 `/api/status` 与 `Settings.from_env()` 均确认ASR未配置。

## 基本回归与正式资料保全

相关现有回归命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_adapters.py tests/test_app.py tests/test_link_import.py tests/test_download_media.py tests/test_local_media.py -q --basetemp=.runtime/phase1-supplement-pytest -p no:cacheprovider --tb=short
```

结果：**69 passed in 24.11s**，退出0。覆盖链接校验、下载任务、缓存转写、上传及媒体元数据等。涉及外部平台/ASR成功的自动测试使用显式替身，仅证明接口与状态流程回归通过，不代替上述实测。

正式服务 `http://127.0.0.1:8765` 保持在线。验证前后正式资料列表数量及规范JSON的SHA256一致，详见平台报告的 `production_documents_unchanged=true`。本轮未改动产品源码、正式数据、模型配置、系统网络配置或浏览器会话，未重启正式服务。新增内容仅为测试探针、隔离测试资料和本记录。

## 后续修正与验收条件

- 先解决本机域名返回非公网地址与现有下载地址防护之间的冲突，再分别复测两个平台实际媒体获取；不能以关闭地址检查替代修正。抖音此前仍有下载器要求fresh cookies的历史记录，本轮没有到达该步骤，恢复网络解析后可能仍有独立的平台获取问题。
- 准备并配置实际 faster-whisper 模型，再对有语音的已导入媒体运行识别，核对非空文本、时间戳、缓存保留和持久化。当前不能声明识别质量或转写速度已验证。
- 下载错误提示还存在诊断不足：当前非公网地址拦截被统一显示为“平台解析或下载失败：页面可能已改版或没有支持的单文件音视频格式”。这是本轮发现的后续修正点；本轮未修改错误映射。

最终接受状态：**验证已完成，真实功能验收未通过；待下载网络与ASR模型条件修正后复验。** 历史Phase 1/1B/1C接口版接收记录保留，本记录补充当前环境的真实能力边界。
