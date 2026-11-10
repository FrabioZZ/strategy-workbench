# Phase 1 补充修复：平台下载

日期：2026-11-10（Asia/Shanghai）。可见实现工作流由当前聊天承担；协调聊天负责 ASR、部署和最终验收。共享目录 `C:/Users/Admin/Desktop/quant`，非 Git 仓库，无分支或独立 worktree。

## 范围与实施计划

1. 复现系统 DNS 返回保留地址的问题，核查 yt-dlp 请求、重定向和连接地址检查的边界。
2. 以受限公共 DNS 解析作最小验证：仅平台/CDN 域名、TLS 验证、固定解析服务地址；返回地址仍须为公网，实际连接仍固定并校验。
3. 先补失败测试，再实现解析兼容与准确错误提示；保留分享文案、短链、分P和下载限制。
4. 分别真实获取 B站样例及用户抖音样例；抖音只使用合法公开页面媒体数据，不读取浏览器会话或绕过验证码/权限。
5. 跑基本回归，更新下载说明和独立 CLI 打包白名单，记录真实证据及剩余限制供协调验收。

所有探测及媒体写入新的 `.runtime/phase1-supplement-download-*` 目录；不改 ASR、配置、正式数据，不重启 8765。

## 当前根因证据

既有实测与代码确认：`validate_url` 直接检查系统 DNS；当前 B站/抖音域名解析到 `198.18.0.0/15` 保留地址，因此下载在提取页面前被阻止。实际 `socket.connect` / `connect_ex` 防护本身应保留。现有错误映射把保留地址误报为平台格式错误。

## 修复结果

**下载网络兼容修复已实现，Bilibili 真实 API 下载验收通过；抖音仍有平台数据获取阻塞，不能声明两平台均跑通。** ASR与正式服务部署不属于本实现聊天的修改范围。

### 解析与路由

- 新增 `app/adapters/download_network.py`。只在下载子进程安装解析兼容：正常公网系统DNS保持原结果；平台/CDN域名的系统DNS失败或全部返回`198.18.0.0/15`时，使用TLS校验的公共DNS查询公网IPv4。
- 固定引导地址为`dns.alidns.com → 223.5.5.5`，失败时`dns.google → 8.8.8.8`。不经过环境代理、不重新解析DNS服务域名、不跟随DNS服务重定向。每次请求5秒、响应最多64KiB；缓存遵守返回TTL且最多60秒、128个域名。
- 返回的全部地址必须为公网；私网、回环、保留地址、混合不安全结果继续拒绝。`socket.connect`及`connect_ex`检查仍保留，并在命名地址连接前固定经检查的IP。重定向/CDN也经过同一检查。
- 备用解析仅限代码中的平台/CDN域名范围。根据真实B站媒体数据补入精确的`upos-hz-mirrorakam.akamaized.net`，没有放开整个Akamai域名空间。未知域名的合成地址仍拒绝。备用查询只发送域名，不发送视频路径、查询令牌、Cookie或用户浏览器数据。
- 参考：[AliDNS公开API文档](https://help.aliyun.com/en/dns/httpdns-doh-json-api)、[Google DoH JSON文档](https://developers.google.com/speed/public-dns/docs/doh/json)。固定地址TLS查询的实际HTTP 200及公网结果见[DNS实测](../.runtime/phase1-supplement-download-diagnostics/doh.json)。应用不修改系统DNS、系统代理或浏览器设置；此机制并不承诺消除平台或链路本身的间歇超时。

### 格式选择与错误提示

初始解析修复后，B站已能提取分P元数据，但媒体首选路由出现HTTP 567，部分公开音轨路由返回403。应用现在使用yt-dlp的`check_formats='selected'`：对所选格式做小范围可用性检查，继续选择平台已提供的可用音轨/单文件格式。测试临时文件使用当前任务目录；没有引入媒体合并、外部下载器或绕过平台权限。真实回归用本地HTTP服务让首选音轨返回567、次选提供有效WAV，验证整个下载结果，而非只断言配置值。

内网/保留地址和TLS连接异常现在映射为固定中文网络错误。仍不向应用API暴露原始第三方异常、签名媒体URL等细节。短链、分享文案、分P、大小/时长、子进程超时与历史数据行为沿用既有逻辑与测试。

## 真实API验收证据

脚本：[api_probe.py](../.runtime/phase1-supplement-download-diagnostics/api_probe.py)。使用真实`create_app`、API、Jobs、媒体子进程和平台网络，不使用下载或ASR替身；资料库位于新的隔离目录。配置为200MiB / 7200秒媒体、180秒任务超时，不配置ASR、不调用转写/AI。

完整报告：[report.json](../.runtime/phase1-supplement-download-api-1794313437/report.json)。

| 平台 | 输入与任务 | 实际结果 |
| --- | --- | --- |
| Bilibili | `https://www.bilibili.com/video/BV1bK411W797?p=2`；HTTP 202；任务`16a710d6d8244c84879fed7a77d2cdf1` | `succeeded`，`has_media=true`，`awaiting_transcription`；28.50秒完成；媒体GET 200 |
| 抖音 | `https://v.douyin.com/aU0BxZKBvVI/`；HTTP 202；任务`b0f35ecb236b4223bff3935729e05f93` | `failed`，`has_media=false`；22.22秒结束；固定“平台限制”提示 |

B站此次新下载媒体为**M4A音轨，2,170,299字节，97.941111秒，1条音轨、0条视频轨**；PyAV完整解码4218个音频帧。保留来源第2P。SHA256：`c28a3156367a622c9ebd377842b7815f23332526f1d5e7bd9edad898209c4e6e`。该哈希与历史同一音轨一致，但此次是新的真实网络任务，未从旧缓存复制。新文件位于报告中记录的隔离`data/media/7794f514902a470b8da68b609b6cbbfd/16a710d6d8244c84879fed7a77d2cdf1/source.m4a`。

另一次直接下载也成功，见[直接下载报告](../.runtime/phase1-supplement-download-bilibili-1794313372/report.json)，21.516秒。早期受限和宿主网络探测的TLS/超时、HTTP567失败均保留在对应`phase1-supplement-download-bilibili-*`目录，不将这些失败计为成功。

## 抖音剩余阻塞与已做调查

1. 短链现已实际跳转到视频`7664970443358489856`，进入Douyin提取器。yt-dlp 2026.10.26仍报告`Fresh cookies (not necessarily logged in) are needed`；[本轮直接提取报告](../.runtime/phase1-supplement-download-douyin-1794313402/report.json)。这只能证明当前匿名提取器没有拿到媒体详情，不能据此断言必须登录或确认存在验证码。
2. 直接访问公开桌面页及移动分享页均返回HTTP 200，但移动页`window._ROUTER_DATA`没有`videoInfoRes`/媒体数据。只读取了公开页面引用的普通应用脚本，确认其使用`/web/api/v2/aweme/iteminfo/`；未执行安全签名/验证码脚本，也未调用内部服务。
3. 使用分享页正常的公开参数和请求头访问该公开接口，得到HTTP 200、0字节JSON响应；未提供`bdturing-verify`挑战头。见[公开接口状态](../.runtime/phase1-supplement-download-diagnostics/douyin-api-status.json)。因此没有可合法提取的公开媒体URL，本轮没有添加靠猜测或伪造成功的抖音备用提取逻辑。
4. 本轮没有读取个人浏览器Cookie、登录态、凭据，没有求解或绕过验证码/访问权限。若要继续验证该样例，需用户在自己的平台页面确认可正常观看；如平台要求验证，应由用户完成。当前应用不会导入其浏览器凭据；可继续处理用户有权保存并提供的本地媒体。下载专项保持**抖音未通过**，由协调聊天向用户说明并决定后续途径。

## 文件改动与基本回归

- `app/adapters/download.py`：接入受限解析、可用格式检查、准确网络错误。
- `app/adapters/download_network.py`：下载子进程专用解析兼容。
- `tests/test_download_network.py`：合成地址、DNS失败、平台/CDN范围、实际连接IP固定、拒绝内网与不安全DNS答案。
- `tests/test_download_media.py`：真实HTTP格式回退、TLS错误脱敏映射。
- `tests/test_adapters.py`：网络测试恢复解析补丁，避免测试污染。
- `deploy/media-fetch/{build_bundle.py,Dockerfile,.dockerignore}`：加入新模块的独立CLI白名单；`tests/test_media_fetch_validation.py`增加解包后`--help`可启动验证。原来只验证无效输入退出1会把导入错误误当正确拒绝，现已补齐。
- `README.md`下载段落及本记录。未修改`app/config.py`、ASR模块、`.env`、正式`data`，未重启8765。

TDD记录：解析/错误提示先出现6项预期失败；新增真实Akamai域名、HTTP格式回退、CLI解包导入及TLS错误映射各观察到失败后修复。对应检查随后通过。首次全量回归：**229 passed，104条Backtrader既有弃用警告，62.65秒**。新增TLS错误用例后的最终全量回归：**230 passed，104条相同的Backtrader弃用警告，56.29秒，退出0**；无失败测试。

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1-supplement-download-final-tests -p no:cacheprovider --tb=short
```

本实现已做基本自查：需求范围、主要下载流程、短链/分P、拒绝不安全连接、媒体类型及打包独立性。没有做对抗审计。正式部署与独立基本复核交协调聊天；工作流接受状态为**B站下载修复可接受，抖音明确外部阻塞，整体三流程尚不可宣布全部通过**。
