# Phase 1 补充修正 — 独立基本验收

日期：2026-11-10（Asia/Shanghai）。验收聊天 `01a1c562-d188-73d3-8d4a-8af5cac91e14`，协调聊天 `01a1c550-0c08-7340-9336-a1a16f4b2480`。目录 `C:/Users/Admin/Desktop/quant`，非Git仓库，无分支或独立worktree。本次为需求与主流程基本验收，非对抗审计。

**最新状态：第二轮必要修复已复核关闭，当前桌面环境的B站/抖音真实导入和ASR主流程可接受。最终证据与71文件源码哈希见本文末尾“第二轮最终接受结论”。下列首轮部分通过和中间发现保留为历史，不代表当前未关闭状态。**

## 首轮接受结论（历史）

**Bilibili真实音轨导入与本地ASR执行/持久化可接受；抖音导入未通过，整体“三条流程全部跑通”不能接受为已完成。** 没有发现本次变更中需要先修复才能保留B站/ASR功能的明显源码回归。抖音属于仍未解决的真实功能阻塞，不能用自动测试通过、HTTP202、短链可解析或页面HTTP200替代成功下载。

先只读理解范围，再以有界`wait_threads`确认两个实现聊天最终完成，随后独立运行最终源码。真实API、下载器、媒体子进程、模型推理均未使用替身；AI策略提取明确关闭。实现自报仅作为背景，本报告有独立执行证据。

| 要求 | 本轮独立结果 | 接受状态 |
| --- | --- | --- |
| B站指定第2P真实导入 | 21.781秒取得M4A音轨，2,170,299字节、97.941111秒；任务succeeded；媒体GET200 | 音轨导入通过，未取得视频画面 |
| 抖音用户原短链导入 | 26.390秒任务failed；has_media=false；无转写；固定平台限制提示 | 未通过 |
| 导入后语音转文本 | 独立执行的新下载B站媒体产生56段，另有中文参考样本3段；补核协调浏览器真实中文教学样例9段 | 执行与持久化通过；不代表逐字准确率 |
| 正式旧资料保全 | 文档、任务、策略和交易资源表前后行数及逻辑SHA256一致 | 本次验收期间通过；正式重启另验收 |

## 独立测试证据

全部新增证据位于 `.runtime/phase1-supplement-review-20261110`。

- **全量pytest：230 passed，104 warnings，79.59秒，退出0。** 告警为Backtrader既有`datetime.utcnow()`弃用提示。[完整日志](../.runtime/phase1-supplement-review-20261110/pytest.log)。覆盖短链/分享文案、分P、任务、下载限制、本地媒体、ASR解码及交易等既有流程；含替身的单元测试不代替真实平台结果。
- **验收边界检查：9 passed，1.99秒，退出0。** 仅写在隔离目录。检查TLS证书/主机名验证、固定DoH引导IP、5秒socket超时、64KiB响应限制、拒绝重定向/截断/问题域名不匹配/内网答案、TTL和128项缓存边界、connect与connect_ex均向底层传递已检查的公网数字IP。[脚本](../.runtime/phase1-supplement-review-20261110/test_review_boundaries.py)、[日志](../.runtime/phase1-supplement-review-20261110/boundaries.log)。仅替换DNS/HTTP传输来覆盖明确边界，调用真实解析/连接保护逻辑。
- **独立CLI包检查通过。** 全量测试实际生成两份可复现包并验证清单；另解包运行`python -I .../validate_media_fetch.py --help`，退出0、无stderr。新网络模块在包内，14个源文件清单哈希匹配（ZIP另含manifest共15项）；Dockerfile和`.dockerignore`也包含新模块。包SHA256：`b0e51f5cbe045f4067d9fd486e8674e106596a57969e6dc20253cdc02b7866ca`。[报告](../.runtime/phase1-supplement-review-20261110/bundle-report.json)。本轮未启动Docker/Linux部署。
- `python -m pip check`：`No broken requirements found`，退出0。实际版本：yt-dlp2026.10.26、PyAV18.1.0、faster-whisper1.2.1、CTranslate2 4.8.5。独立下载包仍固定PyAV19，范围仅下载/探测；产品ASR环境为18.1.0。

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1-supplement-review-20261110/pytest -p no:cacheprovider --tb=short
.venv/Scripts/python.exe -m pytest .runtime/phase1-supplement-review-20261110/test_review_boundaries.py -q --basetemp=.runtime/phase1-supplement-review-20261110/boundary-tmp -p no:cacheprovider --tb=short
.venv/Scripts/python.exe -m pip check
```

## 真实主流程与识别质量边界

[独立探针](../.runtime/phase1-supplement-review-20261110/live_review.py)使用生产`create_app`、API/Jobs及媒体子进程，资料库为`live-data`，任务上限600秒，大小/时长仍为默认200MiB/7200秒。运行时间20:27:54–20:30:28（Asia/Shanghai）。[完整报告](../.runtime/phase1-supplement-review-20261110/live-report.json)。探针退出0仅表示检查完成，各平台按实际结果判定。重跑请复制到新的同级review目录，避免覆盖或向本次测试库追加记录。

**B站：** 输入`https://www.bilibili.com/video/BV1bK411W797?p=2`。本次新建资料和任务，未复制旧缓存。元数据、保存来源均保留`p=2`。1条音轨、0条视频轨，完整解码4218帧；本地文件和媒体API响应SHA256均为`c28a3156367a622c9ebd377842b7815f23332526f1d5e7bd9edad898209c4e6e`。随后手动转写HTTP202，实际生成56段，时间戳有限且各段起止合法、在源音轨时长内，转写后媒体哈希不变、状态transcribed。关闭再新建应用后56段哈希一致，重复转写409，没有覆盖原文。

**抖音：** 输入用户原短链`https://v.douyin.com/aU0BxZKBvVI/`。HTTP202创建任务，最终failed，未生成媒体或文本；错误中无第三方原始URL、Cookie或令牌。实现报告指出匿名提取器要求fresh cookies、公开分享页无媒体数据；独立API复现平台限制，但未据此断言用户必须登录或存在验证码。当前该项不接受。

**中文参考：** 另用[独立上传探针](../.runtime/phase1-supplement-review-20261110/chinese_review.py)将明确标注的Windows离线中文合成音频上传到`chinese-data`，运行真实自动ASR。15.399002秒、679,142字节，SHA256 `69ff02de64be667a04369cb75aca32fa9d6517fdec0a9c31c0964d45f36a0cde`；16.406秒生成3段，时间0.00–14.70秒。新建应用后文本一致、媒体GET200且哈希一致、重复转写409。对照原文仍有“校对→校队”误字，未润色或替换输出。[完整报告](../.runtime/phase1-supplement-review-20261110/chinese-report.json)。这是合成语音，不是真人教学样本。

B站第2P样例为日语内容相关素材，ASR实现侧另测为ja，而产品固定`language="zh"`。本次56段只证明推理/持久化可执行，不证明文本忠实；有可疑转写/重复，不能作为中文教学识别质量依据。独立有参考原文的质量检查覆盖短合成音频；下述补充另覆盖真实平台中文教学流程，但仍未验收逐字准确率、证券术语及数字准确率。没有伪造ASR服务、用样例文本替代推理或远程AI提取，但这也不等于模型不会误识或幻觉。

### 补充：协调浏览器真实中文教学流程

协调在同阶段通过Playwright运行了`BV1UKcBejEQA`《一分钟搞懂一个量化策略：#02 突破形态》的真实网页导入、播放、点击转写及刷新流程。[完整浏览器报告](../.runtime/phase1-supplement-e2e-1794313723897/report.json)。这是新下载的真实平台中文教学素材，区别于前述合成参考音频和日语第2P样例。

本验收随后读取该报告和执行脚本，实际查看[1440截图](../output/playwright/phase1-supplement-bilibili-1440.png)与[390截图](../output/playwright/phase1-supplement-bilibili-390.png)，并以只读SQLite独立核对保存内容、完整解码该媒体；没有在本验收聊天重复执行浏览器脚本。核查证据见[补充复核记录](../.runtime/phase1-supplement-review-20261110/coordination-chinese-evidence.json)。

- 实际M4A为635,716字节、29.674921秒，1音轨/0视频轨，完整解码1278帧；SHA256 `dbbfad29d469dda040b3808d57448912823674d2590c04e01590e88863e946e4`。保存来源为规范B站视频URL，无分享跟踪参数。
- 浏览器报告记录播放进度0.318899秒，点击转写HTTP202，27.643秒产生9段中文，任务succeeded；刷新后内容一致。独立读取SQLite确认9段与报告完全相同，所有起止时间合法且在音轨范围内。
- 脚本对1440/390宽度均检查无横向溢出；报告0个page error。两张截图中转写、音频播放器和保存状态可见，未见明显布局溢出。
- 最后一段“先行、三角形和举行形态”等术语仍可疑，未经逐字听校，不能声明高准确率。该证据补齐真实中文教学媒体的网页链路，识别质量仍需要人工校对。

补核时63个受检源码/依赖/打包文件哈希与原验收清单一致；此补充未修改产品源码，因此未重复全量测试，原230项回归与9项边界检查仍对应当前受检版本。

## 模型与网络防护复核

独立读取[官方固定版本元数据](https://huggingface.co/api/models/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120)，再读本地权重计算SHA256，完全匹配官方LFS对象：`3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`，483,546,902字节。[来源](../.runtime/phase1-supplement-review-20261110/model-source.json)、[本地完整性](../.runtime/phase1-supplement-review-20261110/model-integrity.json)。未重复下载模型。真实任务配置CPU/int8，适配器`local_files_only=True`，工作进程HF离线；PyAV兼容修复有真实PCM解码回归，业务转写代码没有被替身替换。

源码基本复核：

- 备用DNS仅对明确平台/CDN在系统DNS失败或全部为`198.18.0.0/15`时启用；私网/回环/混合不安全地址仍拒绝。Akamai仅精确允许`upos-hz-mirrorakam.akamaized.net`。connect/connect_ex固定实际受检公网IP，重定向和CDN同样受保护。
- DoH固定公网引导IP，默认SSL上下文校验证书/主机名，不接受重定向，只传域名/A查询。每次socket操作5秒超时、响应最多65536字节、TTL至多60秒、缓存至多128项；5秒不是所有重试的合计墙钟上限，整体仍受工作进程超时约束。
- yt-dlp不读个人Cookie/netrc、不使用环境代理或外部下载器；socket timeout20秒、有限重试，大小/时长前后检查保留。新增格式检查只选择平台返回的音轨/单文件格式，没有引入合并或放开内网；分享文案、短链、分P回归通过。
- 未新增抖音公开页面fallback，没有匹配视频ID的新提取分支需要接受；也没有验证码绕过或个人会话读取实现。今后若新增，应单独验证仅接受原视频ID匹配的单视频公开媒体。
- ASR来自实际模型分段，已有文本拒绝重复覆盖，缓存保留。推理成功与识别准确率分别报告。

## 正式资料保全、脱敏与受检版本

本验收仅在review目录写脚本/数据/证据，并更新本报告；未改产品代码、`.env`或正式data，未重启8765。正式SQLite以`mode=ro`、query_only及只读事务读取表内容，仅记录逻辑哈希和数量，不复制正文。前后均为文档2行、任务2行、策略0行、交易resources1行，所有逻辑哈希及正式文档列表哈希一致。当前两份正式文档均无媒体引用，故没有旧媒体文件需要逐字节比较；[核对记录](../.runtime/phase1-supplement-review-20261110/production-media-current.json)。正式重启后的保全仍归协调工作流。

下载/ASR最终文档链接的12份JSON已检查，未发现临时CDN URL或分享跟踪参数；[扫描记录](../.runtime/phase1-supplement-review-20261110/evidence-scan.json)。此前提醒的诊断`routes.json`在最终复核时，Location已是无查询参数的视频路径，没有遗留分享参数；另保留[脱敏副本](../.runtime/phase1-supplement-review-20261110/routes-sanitized.json)。最终证据须继续使用脱敏版本，不发布早期原始网络响应或带签名URL的诊断内容。

受检63个源码/测试/依赖/打包文件完整SHA256见[源码清单](../.runtime/phase1-supplement-review-20261110/reviewed-source-hashes.json)。真实探针开始、结束、清单生成时共同源码哈希一致。关键文件：

| 文件 | SHA256 |
| --- | --- |
| app/adapters/download.py | `dcf933b24f3a3f9bfc4e5153915d655abd885336e4b98159f15873c8dce87457` |
| app/adapters/download_network.py | `081ba88ebc6af7c419fc089edd4d7d905f83c9e47b3c10eac2b7a137c564fd3f` |
| app/adapters/asr.py | `8adc1806800f10adccc865074f50c0b7d734398d36cf6434f5df4d35a1a578ca` |
| requirements.txt | `6a726275378b278f5e10c41cf56ea07666dcb505f8e4f9e60f1b15c5053393b6` |
| requirements-lock.txt | `ed940a7b545b99f0a41d4289b114f16322702e4b417baad942981ea53bba3b06` |

协调浏览器真实中文教学结果已按上节补核，明确区分本聊天独立运行的API/子进程测试和协调执行的浏览器测试。正式部署/重启不属于本报告已完成范围。

**整体接收前必须关闭的事项：** 抖音指定短链仍无法取得媒体，需要取得实际可访问的单视频媒体并复验，或由用户明确接受该能力尚未实现的限制。不能将本地文件上传记为抖音链接流程通过。B站音轨导入和CPU ASR路径可先保留/部署；正式重启由协调备份并检查无活跃任务后执行。未发现额外必须修复的明显源码缺陷；本阶段基本验收状态为**部分通过，抖音阻塞未关闭**。

抖音同阶段必要跟进聊天为`01a1c56d-c228-7243-8fb1-457db0499a5c`。协调通知其目前仅只读调查，未改产品；当前基本验收无需等待未来改动。若该跟进产生源码修改，应在本阶段针对新版本安排复核，本报告不自动覆盖未来版本。

## 抖音跟进后的第二轮复核（过程记录）

协调随后通知抖音跟进已进入产品匿名浏览器桥实现。本验收继续在同一可见工作流进行，用`wait_threads`等待该聊天最终完成后检查最终源码和文档，当前不提前给出第二轮接受结论。证据目录为`.runtime/phase1-supplement-review-douyin-20261110`。

本轮独立执行原短链及B站API下载、媒体完整性/身份核对、网络保护/浏览器生命周期/依赖打包检查与必要全量回归；为避免重复长ASR争用CPU，352秒抖音全文转写由协调执行，本验收另核对其持久化产物。ASR业务未变时保留首轮独立模型/路由证据，有新疑点再追加检查。正式8765已由协调备份重启，本验收不操作其运行状态。上述首轮“部分通过”结论保留为历史，未来源码不由首轮哈希自动覆盖。

### 第二轮必须修复项（历史复现，已在末节关闭）

1. **[P1] 短链最终详情没有绑定解析出的原视频ID。** `app/adapters/download_browser.py:211`已得到`browser_url`（原短链解析出的规范视频页），但232行仍调用`validate_result(raw, url)`传入原短链。74行又对短链跳过目标URL比较；Node桥33行依据当前`page.url()`取ID。如果页面后续跳到另一单视频，桥返回该视频的URL与同ID详情，Python会接受。独立复现使用真实`get_public_detail`，仅替换子进程传输：解析目标固定为`7664970443358489856`，桥返回`1111111111111111111`的自洽URL/详情，实际被接受。应将最终结果绑定已解析的`browser_url`及其视频ID，并覆盖短链解析后页面切换到另一视频的回归。这不否定本轮实际下载拿到了正确目标，但当前缺少任务明确要求的目标身份约束。
2. **[P2] 独立CLI运行时环境丢失Node路径。** `scripts/validate_media_fetch.py:128`把worker的PATH设为Python目录，新增桥却以`shutil.which('node')`查找Node。当前普通环境可找到`C:/Program Files/nodejs/node.EXE`，实际CLI worker环境返回null；原短链CLI命令实际退出1，1次尝试0成功。安装了Node/Chrome和项目npm依赖仍不能恢复该CLI路径，单纯打包新文件或`--help`成功不足以证明功能可运行。应以受控方式传入必要Node可执行位置/路径，继续排除代理和凭据，补解包后真实运行条件检查。

复现数值见[findings-reproduction.json](../.runtime/phase1-supplement-review-douyin-20261110/findings-reproduction.json)；实际CLI报告见[phase1c-cli-runtime/report.json](../.runtime/phase1-supplement-review-douyin-20261110/phase1c-cli-runtime/report.json)。上述均未修改产品代码；协调需安排同阶段修复后复核。本轮其它边界和最终证据仍在整理，未给出无保留接受结论。

### 第二轮已取得的独立证据

对抖音初次冻结交付版本（修复上述两项前），本聊天独立运行真实API→Jobs→子进程下载：B站第2P用时28.719秒，2,170,299字节/97.941111秒M4A，完整解码4218帧；抖音原短链用时69.734秒，6,514,083字节/352.177007秒MP4，1音轨/1视频轨，完整解码7584帧。抖音规范媒体来源正确匹配`7664970443358489856`，SHA256为`713b54ff5cb72998f5cdf969e603e5fce4591befd9fb789df75b4b984301d560`。两者任务succeeded、媒体GET200、响应哈希等于文件哈希；新建应用后媒体保留。正式两库及资料列表的逻辑哈希前后一致。[独立报告](../.runtime/phase1-supplement-review-douyin-20261110/live-report.json)、[探针](../.runtime/phase1-supplement-review-douyin-20261110/live_review.py)。这证明实测目标下载成功，但不豁免上节发现的未绑定目标ID分支。

该中间交付版本独立全量测试为**255 passed，104条既有Backtrader弃用警告，89.74秒**，Node详情检查1项通过；[日志](../.runtime/phase1-supplement-review-douyin-20261110/pytest.log)。后续修复将改变版本，不能把此数目自动当成最终修复版回归。

本聊天另运行实际产品Node桥、项目playwright-core及系统Chrome，不使用NODE_PATH；以关闭父IPC模拟取消，观察到8个Chrome子进程及1个conhost，0.219秒结束，观察列表中无遗留子进程。桥的HTTP/HTTPS loopback输入也均未连接到本地目标；该检查可能在启动浏览器前拒绝输入，**不单独宣称它证明了浏览器原生代理路由**。[脚本](../.runtime/phase1-supplement-review-douyin-20261110/browser_runtime_check.py)、[结果](../.runtime/phase1-supplement-review-douyin-20261110/browser-runtime-report.json)。取消测试阻断了外部连接，只验证生命周期；正式代理公网检查由真实下载、源码及边界测试共同覆盖。

协调的新[抖音浏览器E2E报告](../.runtime/phase1-supplement-e2e-1794316457625/report.json)记录：原短链下载68.886秒，实际播放0.314892秒，转写284.656秒生成205段，刷新后保存一致，1440/390均无横向溢出、0个page error。本聊天实际查看两张[桌面截图](../output/playwright/phase1-supplement-douyin-1440.png)/[窄屏截图](../output/playwright/phase1-supplement-douyin-390.png)，只读查询其SQLite并完整解码媒体，确认205段与报告完全一致、非空和时间戳均有效，末段350.16–352.08秒，媒体哈希与上述独立下载一致。[独立产物核对](../.runtime/phase1-supplement-review-douyin-20261110/coordination-asr-evidence.json)。整段ASR由协调执行，本聊天未重复推理；ASR业务源码未变，首轮模型/路由证据继续适用。未做逐字准确率或术语质量保证。

## 第二轮最终接受结论（2026-11-10，21:45）

**当前受检桌面版本可接受，两项必须修复发现均关闭，无剩余必须修复项。** B站和抖音真实API导入均有本聊天独立成功证据；抖音最终修复版还通过独立新源码包安装和真实CLI原短链下载。ASR保留首轮独立模型/路由验证，并补核协调真实网页205段持久化产物。此次为基本复核，不扩展为对抗审计或准确率保证。正式重启由协调按已备份部署流程执行，本聊天未操作8765服务状态。

### 缺口关闭与最终验证

1. **目标身份已固定。** Python现在将受保护短链解析得到的`browser_url`传给最终结果校验，并拒绝把未解析短链当作校验目标；Node `observeDetails`在注册监听时固定原规范URL/ID，不再从后续`page.url()`取目标。本聊天的独立父流程测试验证原目标可接受、另一自洽视频URL/ID必须拒绝。Node测试另验证页面跳往推荐视频时仍只能接收原ID。原[P1]关闭。
2. **CLI运行时已恢复并保持配置隔离。** worker PATH仅含当前Python及已发现Node所在目录；Windows只额外保留系统程序安装根目录，在隔离home创建空`AppData/Local`与`AppData/Roaming`。不恢复个人HOME、代理、密钥、NODE_PATH、NODE_OPTIONS或PYTHONPATH。独立源码包在新目录安装依赖后真实下载成功，见下。原[P2]关闭。
3. **超时清理报告已修复。** 路径仍先验证位于当前任务目录，终止子进程后对Windows残余句柄最多等待2秒；永久清理失败返回明确`cleanup_error`并保留报告，不能将残片计作成功。最终全量包含真实Windows文件句柄及持续清理失败回归，均通过。实现侧历史180秒失败保留，不由后续成功覆盖。

最终版本由本聊天独立执行：

| 检查 | 实际结果 |
| --- | --- |
| 全量Python | **262 passed，104条既有弃用警告，38.76秒，退出0**；[日志](../.runtime/phase1-supplement-review-douyin-20261110/pytest-final.log) |
| 独立目标ID/DNS边界 | **11 passed，0.63秒，退出0**；[合同检查](../.runtime/phase1-supplement-review-douyin-20261110/test_review_contracts.py)、[日志](../.runtime/phase1-supplement-review-douyin-20261110/contracts-final.log) |
| Node生产监听与详情 | **2 passed，退出0**，含页面跳转后保持原目标 |
| Python依赖 | `pip check`无损坏依赖 |
| 独立打包/安装/CLI | 新包清单校验、解包、`npm ci --ignore-scripts`和原短链下载均退出0 |

独立[打包验收脚本](../.runtime/phase1-supplement-review-douyin-20261110/package_check.py)从冻结源码重新生成包，清单18个文件全部核对SHA256（另加manifest共19项），解到`standalone-final`新目录；使用空npm用户/全局配置及独立缓存执行锁定安装。实际加载`standalone-final/node_modules/playwright-core/index.js`，无Codex内部库或NODE_PATH回退。包SHA256：`e1ff4d1862f042c4d2b78e0fa4f051c0cce03b2b34bf5ab14cb1d9e69737daaa`。

随后**运行解包后的CLI**处理用户原短链，配置300秒任务/360秒批次（现有CLI硬上限内）、32MiB/600秒媒体，**实际43.922秒成功**，退出0。规范来源为`https://www.douyin.com/video/7664970443358489856`。新文件6,514,083字节、352.177007秒、1视频轨/1音轨；本聊天再次完整解码7584帧并计算SHA256 `713b54ff5cb72998f5cdf969e603e5fce4591befd9fb789df75b4b984301d560`，与独立API和协调网页媒体一致。不是复制旧文件，也不是只验证`--help`。[安装/打包结果](../.runtime/phase1-supplement-review-douyin-20261110/package-final-report.json)、[独立CLI报告](../.runtime/phase1-supplement-review-douyin-20261110/phase1c-cli-final/report.json)、[最终媒体及保全核对](../.runtime/phase1-supplement-review-douyin-20261110/acceptance-final.json)。

### 浏览器网络与生命周期结论

源码、生产路径及边界测试共同确认：匿名Chrome使用固定本地CONNECT代理，显式取消loopback直连例外，禁用QUIC与未代理WebRTC UDP、阻止service worker；代理只允许精确白名单主机/443，全部DNS答案检查公网后向受检数字IP连接，并核对实际peer。Chrome继续端到端校验TLS，没有忽略证书参数、TLS解密、个人profile读取或登录凭据导入。匿名访客初始化自然加载平台页面；遇到明确验证提示停止，不求解验证码。

代理32路并发、最多10秒等待、5秒空闲回收、80MiB总流量和150秒截止保持；浏览器120秒及父级135秒上限保留，整个任务还受外层超时约束。详情只经内存IPC交给下载器，最终媒体继续既有连接/大小/时长检查。父IPC关闭的独立Chrome清理结果见前节；CLI进程树终止和退出清理也在最终全量回归覆盖。没有把普通页面HTTP200或匿名会话建立算作媒体成功。

最终API、独立CLI、协调ASR等主要JSON证据未发现临时CDN URL、分享跟踪参数或Cookie值。最终只读复核再次确认正式两库各表逻辑哈希与本轮开始一致；本聊天未写正式data。失败/超时记录保留，但不作为成功计数。

### 最终受检版本与限制

最终71个文件哈希清单：[reviewed-source-hashes-final.json](../.runtime/phase1-supplement-review-douyin-20261110/reviewed-source-hashes-final.json)。已包含协调最后更新的README，以及Python/Node产品与测试、依赖锁、CLI、Docker白名单和runbook；末次核对无变化。清单映射的SHA256为`9ef468194599f1248c8832d46c5aa308a41b420f98ec30126384c0703b763c41`。ASR、Jobs、media_worker、main与config哈希和首轮完全一致，故未重复352秒推理。

| 关键文件 | 最终SHA256 |
| --- | --- |
| app/adapters/download.py | `6b39b7008291c7c92e93d7afb1bbb8880ec97198287c0381b0c35144cca31067` |
| app/adapters/download_network.py | `89cc774b5f3bf327aac0e01101369731a426c073e23b3af136c111c5041cde83` |
| app/adapters/download_browser.py | `69e64ba11d11831620e775cff04aa4d896fb559e55b6148aa65e23347b1458eb` |
| app/adapters/douyin_browser.cjs | `1823739335deb564b99ff17f09ea2e2ce4d37ff2730255d8254fc19952cf64f3` |
| scripts/validate_media_fetch.py | `2195eade350db383b891e14623df49a36cbe827de49f576af3e56d0a8d5b56de` |
| package-lock.json | `8fd2381c3c58e0410b764eee261aeac3214a890f7d9479186f308dbec208aa7b` |
| README.md | `6e490628f2b74ed4b53986b85730ed2e18582f5f5189ec99e8ac956f493454bb` |

接收范围是当前Windows桌面环境及上述公开样例：外部DNS/CDN/平台仍可能间歇失败；普通失败不能伪报成功。基础Docker镜像没有安装Node/Chrome，本轮没有宣称Linux/容器抖音通过。ASR术语、数字及逐字忠实度仍需人工校对；B站示例取得的是音轨，抖音示例取得音视频。正式重启及重启后服务检查归协调执行。**至此本次独立基本复核闭环完成，无未关闭必须修复项。**
