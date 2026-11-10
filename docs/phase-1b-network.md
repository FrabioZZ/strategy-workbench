# Phase 1B 真实平台验证

日期：2026-11-09（Asia/Shanghai）。执行环境为本项目 Windows Python venv、yt-dlp `2026.10.26`。这些结果来自真实网络，不是单元测试替身。

## 样例与边界

样例取自已安装的官方 yt-dlp extractor `_TESTS`：

- B站：`https://www.bilibili.com/video/BV1bK411W797?p=2`，官方 [BiliBiliIE 源码](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py) 中公开的多P样例，明确选择第2P。
- 抖音：`https://www.douyin.com/video/6961737553342991651`，官方 [DouyinIE 源码](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/tiktok.py) 中公开样例。

仅进行小样本测试，先取元数据；使用应用的实际连接地址检查，不读取浏览器cookies，不配置账户、付费或绕过验证码。探测脚本为 `.runtime/phase1b-network-probe.py`，输出只含必要元数据和安全错误分类，不记录下载地址、签名或原始请求。

## 元数据结果

| 平台 | 结果 | 实际证据 |
| --- | --- | --- |
| B站 | 成功 | 返回 `BV1bK411W797_p2`；标题“物语中的人物是如何吐槽自己的OP的 p02 帰り道/894+羽川”；时长97.941秒；9个媒体格式；1.64秒完成 |
| 抖音 | 平台限制 | `DownloadError`，要求cookies/登录；0.53秒返回；未取得媒体 |

机器可读结果保存在 `.runtime/phase1b-network/bilibili-metadata.json` 和 `douyin-metadata.json`。

## 产品路径验证

协调隔离服务使用 `.runtime/phase1b-live-data`、端口8768；限制16 MB、180秒媒体时长、150秒单任务运行时间。未配置ASR或AI。通过Chrome真实页面粘贴含追踪参数的分享文案，服务端保存规范化的 `?p=2` 来源。

| 平台 | 产品实测 | 结果 |
| --- | --- | --- |
| B站 | 页面提交 → 后台真实下载 → 缓存元数据 → 页面播放 | 成功。缓存M4A **音频**，2,170,299字节；PyAV核实97.941111秒；标题及第2P来源保留。状态 `awaiting_transcription`，下载任务成功，无转写段落。Chrome播放时间实际前进约0.82秒；390px窄屏无横向溢出；0个page error |
| B站无ASR转写入口 | 对已缓存媒体请求手动转写 | HTTP409，提示配置本地ASR并重启；缓存保留，没有假文本、没有新下载 |
| 抖音 | 分享文案提交 → 真实下载worker | 正确显示媒体获取失败及平台限制提示；`has_media=false`。底层与先前元数据探测一致要求cookies/登录。**未成功下载抖音媒体** |

每个平台仅一个公开视频样例；抖音仅先行元数据探测和一次产品路径验证，不循环重试，不获取登录信息。不得据此声称所有B站视频可用或抖音下载成功。短链和其它分P输入边界由回归测试覆盖，尚无用户实际分享短链的网络实测。

证据：

- `output/playwright/phase1b-live-result.json`：B站下载、元数据、浏览器播放及未配置ASR响应。
- `output/playwright/phase1b-live-audio.png`、`phase1b-live-mobile.png`：真实缓存音频页面。
- `output/playwright/phase1b-douyin-result.json`：抖音真实失败状态和安全中文提示。
- `.runtime/phase1b-live-browser.cjs`、`.runtime/phase1b-douyin-api.py`：协调复现脚本，未修改产品下载行为。

此验证不等于所有URL可用，不证明真实ASR或LLM可用；这两个服务目前未配置。

## 用户实际分享文案（优先结论）

用户提供《股市生存指南》第32课“RSI&amp;MACD双剑合璧”整段分享文案，包含 `https://v.douyin.com/aU0BxZKBvVI/`。**上述标题只来自用户文案，尚未从平台元数据取得，不能把文案当作平台已验证标题。**

产品实际入口 `POST /api/documents/url` 接收完整文案返回HTTP202，正确抽取唯一短链并保留原始短链来源。测试使用独立 `.runtime/phase1b-user-data` 和8769端口，使用默认200 MB / 120分钟媒体上限与300秒任务上限，无ASR/AI。

- 无凭据重定向核验：短链302 → `https://www.iesdouyin.com/share/video/7664970443358489856/` 302 → `https://www.douyin.com/video/7664970443358489856` 200。日志只保留路径，去掉查询参数。短链可跳转，不能归因于短链失效。
- 真实产品worker结果：`download_failed`、`has_media=false`、元数据为空；显示安全中文平台限制提示。
- 额外仅元数据诊断确认：yt-dlp `2026.10.26` 抛出 `DownloadError`，**提示需要新的会话 Cookie（fresh cookies）**。这是下载器在未取得 `aweme_detail` 时自行抛出的提示，不是平台明确确认“Cookie过期”，也不等同于证明必须登录账号；应用将其归类为安全的“平台限制”提示。尚未取得可信平台标题、实际时长、体积或媒体文件；并非超过200 MB/120分钟限制，也不是ASR阻塞。
- 没有导入用户cookies、读取浏览器账户、使用付费或签名服务，也没有反复重试。当前可用回退是用户自行取得有权使用的媒体后本地上传。此条结果是当前用户抖音视频的实际结论，优先于旧公开样例。

证据：`output/playwright/phase1b-user-douyin-result.json`、`phase1b-user-douyin-redirect.json`、`.runtime/phase1b-network/user-douyin-metadata.json`；复现脚本 `.runtime/phase1b-user-douyin.py` 保留完整待解析分享文案，未把文案当作指令。
