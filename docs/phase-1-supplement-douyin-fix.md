# Phase 1 补充修正 — 抖音匿名媒体加载跟进

**独立复核修复完成（2026-11-10）：源码已重新冻结，262项Python及2项Node测试通过，原短链隔离CLI真实下载成功，实际53.125秒。** 视频目标身份已在JS与Python两端固定；CLI已修复Node/系统Chrome发现、空白隔离AppData目录和退出清理报告。最终取得6,514,083字节、352.177007秒MP4，目标ID正确，完整解码7584帧音频；CLI任务上限300秒，实际耗时仍小于原180秒，上轮180秒失败证据保留。经require_escalated同执行环境对照确认Chrome启动修复，完整证据见末尾。协调已另行完成工作台播放→352秒ASR205段→刷新验收，本轮未重复长ASR、未重启8765，可交独立基本复核收口。

**此前API下载结果：原抖音短链两次通过独立真实应用API下载。** 两次耗时91.67秒和76.45秒，均取得6,514,083字节、352.177007秒MP4（1视频轨/1音轨），完整解码7584帧音频，媒体GET 200，状态为“已获取，待转写”。第二次在`npm ci`重装后运行，两次均移除NODE_PATH；都是新的API→Jobs→媒体子进程→真实平台网络任务，不使用既有诊断文件或替身。两次之间的一次公共DNS暂时失败也保留，未当作成功。

完整ASR与正式8765浏览器E2E由协调另行完成；本聊天未重启8765、未改ASR/`.env`/正式data。以下早期检查点保留失败与定位过程，不代表最新结果；以首段及末尾复核修复交接为准。

日期：2026-11-10（Asia/Shanghai）。工作目录 `C:/Users/Admin/Desktop/quant`，非 Git 仓库，无独立分支。当前可见跟进聊天负责抖音下载，原下载聊天已完成（通过 `wait_threads` 确认）。不修改 ASR、`.env`、正式 data，不重启 8765。

## 计划与边界

1. 从原浏览器证据继续，检查全新匿名 Chrome 的请求失败、脚本错误、未完成请求和页面状态；仅观察公开页面的自然加载。
2. 区分网络、未完成公共访客会话与明确验证码/登录要求；测试有时间上限，不读取个人 profile，不记录 Cookie 值或临时 CDN URL，不求解验证。
3. 只有根因证据支持且有可重复应用接入路径时才改下载代码；以失败测试先行，保留地址防护、真实出站公网检查、大小/时长/任务超时。
4. 记录真实媒体证据或精确阻塞，交协调与独立基本验收复核。浏览器页面打开不计作应用成功。

## 初始证据

- 原下载实测：短链已解析到 `7664970443358489856`；yt-dlp 提示 fresh cookies；公开移动接口返回 HTTP 200、空正文。
- 原浏览器实测：全新匿名上下文自然生成访客 Cookie，但15秒后仍为“视频数据加载中”，没有 video 元素或 aweme 响应。
- 本轮调查进行中；探针 `.runtime/phase1-supplement-douyin-fix/probe.cjs` 仅保存脱敏诊断。

## 调查检查点（20:35）

- 新匿名桌面上下文延长至60秒仍无 video 元素、无 aweme 媒体详情请求、无明确验证码/登录门槛。DOM为 interactive，83个同一静态CDN上的播放器/应用脚本仍 pending；其中包括 `routes-Video-id-route` 和多个 `client-entry`。没有 JS pageerror。
- 58个 `ERR_BLOCKED_BY_CLIENT` 为非HTTP的 `chrome-extension:` 探测请求（首版脱敏显示 null，后续按协议确认），不能把它们当成平台服务被封；另有 `mssdk.bytedance.com` 的两个普通访客初始化请求连接关闭。
- 针对一个 pending 的公共播放器脚本，Python标准TLS读取可在约2.3秒取得357,887字节；系统合成路由与固定公网IP均HTTP200。同一静态域名不是完全不可达。`mssdk.bytedance.com` 根路径系统路由HTTP404，公网直连12秒超时；这不证明API权限条件。
- 正在做延长自然加载至180秒的桌面观察及独立移动匿名页面观察。尚未改产品代码，尚未取得媒体，不能据此要求用户登录或宣布应用成功。

证据：`.runtime/phase1-supplement-douyin-fix/desktop.json`、`network.json`；截图 `output/playwright/douyin-fix-desktop.png`。

延长探针首轮 `long.json` 遇到中间页面尚无 body 的诊断异常（navigation timeout），未实际完成180秒观察。已修正探针空body处理，重跑 `long2`；不把诊断脚本失败归为平台限制。

## 后续进展

- 用户通过协调确认：原链接在其平常App/浏览器可正常播放，中途的登录提示可关闭后继续播放；不能以必须登录作为前提。没有提供或读取其个人Cookie。
- `mobile.json`：新的匿名移动上下文自然从 www 跳转到 `m.douyin.com/share/video/7664970443358489856`，60秒观察末出现正确标题“《股市生存指南》第32课 技术分析黄金搭档，RSI&MACD双剑合璧。”和有src的视频元素，但readyState=0，尚未验证媒体有效。
- `long2.json`：新的匿名桌面上下文最终完成初始化，浏览器自然发出的 `/aweme/v1/web/aweme/detail/` 返回HTTP200、约111KB JSON，`status_code=0`，包含目标 aweme_detail/video。没有执行手工签名或求解验证。当前提取器只直接请求无访客上下文的API，浏览器正常初始化确实提供了缺失的一步。
- `long2`的页面截图等待字体超时，但上述API证据已保存；2.6秒的页面内辅助视频不能作为目标媒体成功。单独使用全新匿名会话的无签名API请求仍超时，说明不能假设只拷贝Cookie就能复现。
- 目前在新的 `long3` 匿名会话中重复观察目标详情，尝试只在内存内交给既有yt-dlp格式处理及受保护下载；详情/Cookie/临时媒体地址不写磁盘。正式接入仍待真实媒体证据。

## 媒体阶段修复检查点

- HTTP/1.1单变量匿名试验再次自然取得目标详情；无需关闭登录弹窗即可取得详情。`http1-first.json`对应首次尝试，媒体阶段确实进入受保护下载，但因新CDN的合成DNS被拒绝失败。
- 详情公开提供的两个CDN主机是 `v3-dy-o.zjcdn.com` 与 `v5-dy-ov-experiment.zjcdn.com`。已在 `tests/test_download_network.py` 添加两个实际主机及未知同后缀主机的测试：观察到 **2 failed / 17 passed** 后，仅在 `DNS_HOSTS` 添加这两个精确主机。修复后 **19 passed**，未知 `unknown.zjcdn.com` 仍拒绝，真实连接继续固定已验证公网IP。
- 正在用新的全匿名会话复跑目标详情→受保护下载，未把临时地址写盘，也没有移除地址防护。
- 还做了公开IP CONNECT代理诊断（仅诊断脚本，无产品接入），所有已建立远端连接均为公网；匿名页面因若干公共安全初始化脚本网络失败仍未加载完成。没有跳过/伪造这些脚本。代理报告只记录主机/IP/错误类型，不含Cookie、完整URL或TLS内容。
- Python Playwright可选运行时安装下载两次超时，尚未安装成功或加入依赖文件；当前真实浏览器诊断继续使用既有Node Playwright+系统Chrome。

### 真实媒体已取得（应用接入尚待完成）

重复HTTP/1.1匿名会话正常获得目标详情并下载成功，文件 `.runtime/phase1-supplement-douyin-fix/media-1794314878/source.mp4`：**6,514,083字节，352.177007秒，video，有音轨**。浏览器中目标video也实际达到readyState=4、duration=352.167。没有登录、验证码求解、读取个人profile或复制持久化CDN地址。媒体获取使用真实yt-dlp及现有下载网络防护和PyAV检查。

该证据证明匿名正常播放和受保护媒体下载均可行，但当前仍为诊断脚本，不能标记原应用短链入口已成功。正在验证受保护匿名初始化的可重复接入；必要浏览器运行时依赖和生命周期清理也须一并解决。

## 产品接入与当前验收（进行中）

- 新增 `app/adapters/download_browser.py` 和 `douyin_browser.cjs`：每次抖音任务启动全新匿名Chrome，等待官方页面自然返回匹配视频的详情，只经内存管道交给yt-dlp；不模拟签名、不复制个人Cookie，不缓存登录态。
- 所有浏览器出站通过仅允许已观察精确主机/443 CONNECT的本地转发器；DNS结果全量验证后固定公网IP，连接后再核对peer。Chrome仍验证TLS，禁用QUIC和直连绕过；转发总量80MiB、并发32、浏览器120秒（含普通重载最多一次）、父级135秒，继续受原任务总超时限制。媒体阶段继续原大小/时长/公网检查。
- `guarded2.json`已证明这条受保护浏览器连接链可正常取得详情并再次下载6,514,083字节/352.177秒媒体（`media-1794315061`）；不是仅浏览器直连才能成功。
- 新增正常项目依赖：系统Node.js>=20、`package.json`/`package-lock.json`锁定官方npm tarball的 `playwright-core@1.62.1`（SHA512完整性在锁文件）、系统Google Chrome。项目 `node_modules` 已安装，解析路径为项目内 `node_modules/playwright-core/index.js`；无Codex运行库路径，无NODE_PATH要求，无Python新增依赖。
- 初次真实应用API未通过（报告 `phase1-supplement-douyin-api-1794315324`，171.84秒）。定位为原短链先302到 `www.iesdouyin.com/share/video/.../` 再302到www；初版代理漏掉中间主机。已按真实跳转增加精确主机并先观察失败测试后修复。另外避免先浪费约47秒在已知无法初始化访客的裸API上，抖音直接走正常匿名页面，B站保持原链路。
- 接口结果严格核对目标ID、页面域名、来源API、成功状态与video对象；缺失依赖明确提示安装。15项浏览器边界测试、下载/网络/独立打包共88项专项回归已通过（最终全量仍待跑）。
- 父进程取消实测 `cancel.json`：关闭IPC管道后1.391秒退出，捕获的8个Chrome子进程及conhost全部结束，没有遗留进程。
- 第二轮原短链真实API任务进行中，明确移除了NODE_PATH。最终接受仍待该任务与全量回归，不使用首次诊断文件代替新下载。

## 最终实现收敛

后续真实应用调查又找到两个与一次性探针不同的边界：

1. 浏览器瞬时请求超过32路时，初版代理立即关闭新连接，访客初始化资源因此丢失。现改为最多10秒有界等待，5秒无数据的连接回收；仍保留32并发、80MiB、截止时间、公网固定IP和TLS验证。真实本地套接字测试先复现“第二个连接被直接关闭”和“空闲连接不释放”两项失败，再修复通过。
2. 分享短链会附加 `previous_page` 等参数，使页面进入另一套推荐/批量详情流程，甚至跳到精选页。现先在下载子进程经受保护HTTPS解析最多5次已知平台跳转，再用现有URL规范化校验得到不带分享参数的单视频页面。浏览器只读取匹配该视频ID的公开详情，不能拿推荐视频代替目标。规范化、错误页面和跨域目标均有回归。

第三轮API在180秒上限内下载到5,881,815字节片段后被正确中断（`phase1-supplement-douyin-api-1794315978`）；保留此证据，未增大或移除测试上限。最终规范化流程在同一180秒上限内91.67秒成功（`phase1-supplement-douyin-api-1794316169`）。

本次项目依赖复现使用 `npm ci --ignore-scripts` 已成功，锁文件包为官方registry的`playwright-core@1.62.1`，实际加载项目`node_modules`。运行时为Node v24.14.0、已安装Chrome156.0.8078.80。Python Playwright下载尝试未安装成功，最终没有增加Python依赖或引用Codex内部路径。现有基础Docker镜像仅新增源码/依赖声明，不含Node/Chrome，未宣称容器抖音验收通过。

下载代码由每次任务的新Python子进程加载；本次不涉及父服务配置，新增任务可加载新桥和项目依赖，无需因为npm依赖重启服务。正式部署和可见浏览器E2E仍交协调按其备份/部署流程处理。

当前正在进行最终全量测试及npm重装后的第二次独立API下载；结果随后追加。没有重复进行352秒长ASR。

最终全量测试已完成：**255 passed，104条既有Backtrader弃用警告，69.53秒**；`npm run test:browser`也通过。测试命令：`.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1-supplement-douyin-fix/final-tests -p no:cacheprovider --tb=short`。

npm ci后的重复API在最初解析阶段遇到系统合成DNS和两个公共DNS均不可用，11.95秒明确失败（`phase1-supplement-douyin-api-1794316296`），未伪造成功。已保留失败并进行一次新的有界任务复试；不能承诺外部网络每次可用。

## 变更清单与基本自查

- 下载接入：`app/adapters/download.py`、`download_network.py`、新增`download_browser.py`/`douyin_browser.cjs`。
- 可复现运行时：`package.json`、`package-lock.json`；项目安装了`node_modules/playwright-core`。未修改Python依赖、ASR、`.env`或正式资料。
- 回归：`tests/test_download_browser.py`、`test_douyin_browser.cjs`、`test_download_media.py`、`test_download_network.py`、`test_media_fetch_validation.py`。
- 文档与独立源码包：README下载段落、`deploy/media-fetch/build_bundle.py`、Dockerfile与白名单。独立包可重现性、内容边界和解包后CLI启动测试通过；Docker容器运行未测试，浏览器运行时须另装。
- 基本自查覆盖：原短链和规范视频身份、推荐视频不冒充目标、真实媒体与音轨、出站地址检查/固定/peer核对、网络失败不报成功、任务限额、父进程取消、无个人profile及凭据日志、B站与既有应用回归。未进行对抗审计；最终独立基本复核由既有可见验收聊天承担。

桥使用标准[Playwright浏览器上下文](https://playwright.dev/docs/browser-contexts)与[HTTP代理能力](https://playwright.dev/docs/network#http-proxy)，没有注入修改平台安全脚本。

## 最终接受与交接

| 实际任务 | 报告目录（均在`.runtime/`） | 结果 |
| --- | --- | --- |
| `d9fa15bc4fc84ac4885d6af53bdf713c` | `phase1-supplement-douyin-api-1794316169` | 原短链成功，91.67秒，完整MP4/音轨解码/媒体GET200 |
| `0924dd8db855453680c72dfdee850012` | `phase1-supplement-douyin-api-1794316296` | npm ci后公共DNS暂时不可用，11.95秒明确失败，无媒体 |
| `2cc27ed32d514298ba787e71c748ae01` | `phase1-supplement-douyin-api-1794316360` | 新匿名会话、原短链再次成功，76.45秒，完整MP4/音轨解码/媒体GET200 |

两次成功文件SHA256一致：`713b54ff5cb72998f5cdf969e603e5fce4591befd9fb789df75b4b984301d560`；新文件分别位于各自独立资料/任务目录，未复制旧文件。大小200MiB、时长7200秒、任务180秒的隔离验收上限保持不变。

最终代码全量回归：**255 passed，104条既有弃用警告**；Node详情边界测试通过。npm ci可复现、无NODE_PATH依赖、父进程取消清理通过。当前没有未完成的探针/测试会话，不再改产品源码。下载专项接受为**通过**；正式工作台播放、完整352秒ASR、刷新持久化及独立基本复核由协调继续，不在此冒充已验收。未重启8765，未修改正式资料、交易库、ASR或`.env`。

## 独立基本复核后的两项必要修复

复核输入为`.runtime/phase1-supplement-review-douyin-20261110/findings-reproduction.json`，不扩展为对抗审计。

1. **短链目标身份固定。** `get_public_detail`将受保护解析所得`browser_url`传给最终Python校验；校验不再接受未解析短链作为目标。JS的`observeDetails`在注册监听时固定规范URL和视频ID，页面后续跳转不能修改目标。Python真实父逻辑在仅模拟进程传输时验证“原目标通过、另一个相互匹配的URL/ID被拒绝”；Node直接调用生产监听函数验证页面跳到999后不会接收999，仍只能返回原123。Python先出现2项预期失败后通过，Node新增测试先失败后通过。
2. **独立CLI运行时与配置隔离。** PATH仅保留当前Python和父环境已发现的Node所在目录，不复制完整PATH；Windows仅额外保留`PROGRAMFILES`/`PROGRAMFILES(X86)`用于系统Chrome发现。隔离home内建立`AppData/Local`和`AppData/Roaming`，配置变量均指向新目录。代理、密钥、`NODE_PATH`、`NODE_OPTIONS`、`PYTHONPATH`仍清除，项目自己的playwright-core不变。真实Python→Node子进程测试先复现Node无法发现，再验证运行和敏感环境排除；真实Chrome启动测试又复现安装根目录丢失以及空目录结构缺失，修复后通过。

经批准执行环境（require_escalated）的单变量对照在`.runtime/phase1-supplement-douyin-fix/approved-browser-1794317689/report.json`：相同环境缺少AppData目录时Chrome拒绝调试连接；仅创建空目录即成功；最终清理环境和父环境下的独立临时profile均成功。所有实例只打开空白浏览器后关闭，不恢复个人会话。另在同一批准环境执行真实Node/Chrome两项测试：2 passed。

最终产品源码全量回归：**260 passed，104条既有Backtrader弃用警告，38.78秒**，日志`.runtime/phase1-supplement-douyin-fix/review-final-all.log`；Node **2 passed**，日志`review-final-browser-tests.log`。定向浏览器/CLI回归65项通过，独立包可复现性与解包启动包含在全量回归中。

真实CLI保留两次失败：`phase1c-douyin-review-fix-cli-20261110/report.json`（12.922秒，修复Node后暴露Chrome发现问题）；`phase1c-douyin-review-fix-cli-final-20261110/report.json`（138.531秒，未取得媒体，报告仅为download_error，不据此单独断定原因）。当前按协调要求在require_escalated执行环境运行最终源码原短链下载，32MiB/600秒媒体/180秒任务上限未提高；结果随后追加。

本轮改动：`app/adapters/download_browser.py`、`douyin_browser.cjs`、`scripts/validate_media_fetch.py`及三份对应测试，README与`docs/phase-1c-runbook.md`补足CLI运行时说明。未改ASR、`.env`、正式data或8765服务。

### 隔离CLI退出处理与最终回归

获准环境下的180秒任务已开始下载媒体，但截止时仅完成898,727字节，随后退出时未写出report.json，而是输出`invalid_arguments_or_output`。该次记录保存在`.runtime/phase1c-douyin-review-fix-cli-approved-20261110/failure-observation.json`及原残片，不计成功。Windows真实打开文件句柄的回归复现了清理`PermissionError/WinError 32`会中断报告；另用持续清理失败确认报告也会丢失。两项测试均先失败，再修复通过。

修正后，失败媒体清理最多再等待2秒，永久失败转为明确`cleanup_error`并保留报告，不回显底层错误，也不把残片当作成功。README和runbook说明运行时与退出边界。最终全量重新执行：**262 passed，104条既有警告，40.15秒**；Node **2 passed**。日志为`.runtime/phase1-supplement-douyin-fix/review-frozen-tests.log`和`review-final-browser-tests.log`。

最后一次真实CLI使用既有CLI允许的**300秒任务硬上限**（批次360秒），只增加等待预算，仍为32MiB/600秒媒体，不修改应用任务超时配置。独立新目录`.runtime/phase1c-douyin-review-fix-cli-300s-20261110`，获准环境、新匿名会话、原短链，正在运行。保留此前180秒失败；不以扩大时限掩盖原结果。

### 复核修复最终交接

最终CLI **成功，退出0**，实际媒体任务53.125秒、整批53.172秒；原输入`https://v.douyin.com/aU0BxZKBvVI/`，输出规范来源`https://www.douyin.com/video/7664970443358489856`。命令为：

```powershell
.venv/Scripts/python.exe -I scripts/validate_media_fetch.py https://v.douyin.com/aU0BxZKBvVI/ --label local --output-dir .runtime/phase1c-douyin-review-fix-cli-300s-20261110 --task-timeout 300 --batch-timeout 360 --max-mib 32 --max-duration 600
```

报告`.runtime/phase1c-douyin-review-fix-cli-300s-20261110/report.json`与独立媒体检查`media-inspection.json`确认：

- 新下载文件`sample-001/media/source.mp4`，6,514,083字节、352.177007秒、1视频轨、1音轨。
- 完整音频解码7584帧，SHA256 `713b54ff5cb72998f5cdf969e603e5fce4591befd9fb789df75b4b984301d560`，与此前独立应用下载一致，未复制旧媒体。
- 成功任务虽配置300秒上限，实际53.125秒；此前180秒任务失败仍保留，不能由一次成功承诺外部平台或网络每次成功。
- 真实Node/Chrome启动、独立CLI与全部媒体网络均来自项目运行链路；未使用Codex库回退、个人profile或Cookie。`cloud_execution_verified`仍为false。

源码及对应说明已冻结，8个文件哈希记于`.runtime/phase1-supplement-douyin-fix/review-source-hashes.json`。最终回归为**262 Python passed、2 Node passed**；没有未完成的下载或测试会话。两项原复核发现及本轮实测必需的退出报告修正已完成，可交原独立基本复核聊天确认。未重复长ASR，未重启8765，未修改正式data、ASR或`.env`。
