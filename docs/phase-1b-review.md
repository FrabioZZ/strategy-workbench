# Phase 1B — 独立基本验收

日期：2026-11-09（Asia/Shanghai）。可见验收聊天：`01a1bf3f-b0f0-7c50-89e3-36e8ac477f10`。工作目录 `C:/Users/Admin/Desktop/quant`，非 Git 仓库，无 branch/worktree。

## 结论

**发现 1 项 P2 回归，暂不建议将本阶段标为全部通过。** 链接导入、无模型下载缓存、手动转写与失败重试、文本校对、草案提取和导出等已测流程通过；本地上传媒体丢失内嵌播放器，导致原有媒体回听和证据时间跳转不可用。建议协调线程安排同阶段可见修复线程处理 R1，再做定向复核。

本轮仅做需求对齐、主流程和明显回归的基本 review，没有进行对抗审计。先通过 `wait_threads` 等待实现线程 `01a1bf3d-3c3b-7e32-840c-2f04de194daa` 最终完成（其最终报告 69 项测试通过），再开始测试。没有修改产品代码、实现线程测试、正式 `data/`，也没有重启或操作 8765。写入范围仅本报告及自身 `.runtime/phase1b-review-*`、`output/playwright/phase1b-review-*`。

## R1 — P2：本地上传与历史媒体失去播放器及媒体证据定位

- **位置**：`frontend/app.js:56–60` 只根据 `media_metadata.media_type` 决定是否创建播放器，没有类型就清空播放器；`app/main.py:142–144` 本地上传只保存文件路径，没有探测/填写媒体元数据；`app/jobs.py:97` 转写完成只保存原文。因此新上传资料完成转写后仍没有类型。`app/store.py:44–46` 旧库迁移将元数据默认设为空对象，所以原有媒体也进入同一分支。证据按钮在 `frontend/app.js:144` 仅在播放器存在时设置 `currentTime`。
- **触发条件**：上传一个浏览器支持的有效本地音视频文件，或打开没有 `media_metadata` 的旧媒体资料。此次浏览器实测使用自行生成的 3 秒 PCM WAV；这是可正常解码/播放的文件，不是损坏文件或浏览器不支持的格式。
- **复现**：隔离服务上传 WAV → 页面显示“已缓存媒体（类型尚未确认）”且 `#media-player` 数量为 0 → 启用显式测试 ASR，首次模拟失败后重试成功 → 提取测试草案 → 点击 00:01 的证据。文字段落聚焦成功，但播放器依旧为 0，无法回听或定位媒体时间。媒体接口返回与原文件相同的字节。将同样 WAV 通过模拟平台下载路径导入后，页面出现 `<audio>` 且 Chrome 播放时间实际前进，排除了浏览器/文件本身的原因。
- **影响**：本地上传媒体始终只剩“保存缓存文件”；用户无法在校对页回听、播放或点击证据跳转。历史媒体也受同一逻辑影响（历史分支为代码推导，本轮浏览器直接复现的是新上传）。界面仍提示“点击证据时间可定位到本地媒体”，与实际行为不符。文本段落定位、原文保存和 JSON 导出没有因此损坏。
- **建议最小修复**：对本地上传及缺元数据的历史缓存进行受限的本地媒体探测，保存真实 `media_type`、时长等，再让现有渲染分支创建播放器。可使用已有媒体探测能力和受控 worker；探测应保留本地协议限制、超时/大小界限及失败回退，不仅根据文件后缀假定视频，也不覆盖原文/草案。无需重构下载流程。
- **复核标准**：有效 WAV 上传后出现可播放的 `<audio>`；浏览器支持的视频出现 `<video>`；有旧转写/草案的历史缓存完成兼容处理后能按证据跳转到对应时间。校对内容、revision、草案和任务保留。无法探测的文件继续明确提示并可下载；链接下载音频及缓存重试保持通过。
- **证据**：`output/playwright/phase1b-review-browser/result.json` 的 `playerBeforeASR=0`、`playerAfterASR=0`、`citationFocus=true`；`local-upload-before-asr.png`、`local-citation-no-player.png`；对照图 `platform-audio.png`。已实际查看两张桌面截图。独立接口证据 `.runtime/phase1b-review-probe-result.json` 中本地上传 `has_media=true`、`media_metadata={}`。

实现记录明确说明了未知类型本地/历史文件仅提供下载链接；这解释了行为，但并未恢复原有回听与媒体证据定位能力，因此本验收仍将其列为功能回归。

## 独立执行的验证

### 现有测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1b-review-pytest -p no:cacheprovider
```

**69 passed in 5.49s，退出 0**。记录：`.runtime/phase1b-review-pytest.log`。覆盖分享解析、下载与转写状态、缓存重试、旧库新增字段、限制、安全错误、实际 connect/connect_ex 与地址固定、文本和导出等。未用实现线程声称的通过结果替代独立运行。

### 独立补充接口检查

```powershell
.venv/Scripts/python.exe .runtime/phase1b-review-probe.py
```

退出 0，5 组检查通过，另记录 R1 的元数据缺口。脚本和结果分别为 `.runtime/phase1b-review-probe.py`、`.runtime/phase1b-review-probe-result.json`，日志 `.runtime/phase1b-review-probe.log`。隔离数据目录 `.runtime/phase1b-review-probe-404196918f1a48de962a01bc297e0807`。

| 检查 | 独立结果 |
| --- | --- |
| 分享文案、B站/抖音短链、移动域名、分P与追踪参数、重复同链接 | 4 个有效输入规范化正确 |
| 两个不同链接、夹带非支持域名、恶意相似域名、URL凭据、HTTP、重复/无效p | 7 个无效输入拒绝；实际接口不创建资料 |
| 无ASR获取与缓存 | 下载任务成功，`awaiting_transcription`；自定标题保留，平台标题及真实 WAV 的 3 秒/audio 元数据保留；媒体字节一致；无ASR手动转写409且不增加下载 |
| 手动转写失败/重试及完整后续流程 | worker调用严格为 `download, asr, asr`；缓存保留，校对保存、验证草案、证据时间1秒和JSON导出正确；再次编辑后旧草案禁止导出 |
| 重启与安全错误 | 重启后校对原文、旧草案过期状态、任务与媒体元数据保留；外部403/超时/解析异常中的URL及测试token不出现在中文错误中 |

下载、ASR 和 LLM 成功均为**本验收独立实现的明确测试替身**；真实运行的是 API、任务调度、SQLite、文件读写、PyAV 对有效 WAV 的检查。这些结果不证明真实平台下载或真实模型质量。

### 独立浏览器复核

使用项目已有 Playwright 能力，脚本 `.runtime/phase1b-review-browser.cjs` 通过自己的 Python probe 启动并关闭 **8881** 隔离服务。数据目录 `.runtime/phase1b-review-browser-1794211406916`；没有使用 8765 或实现线程服务。命令：

```powershell
# NODE_PATH 指向 load_workspace_dependencies 返回的 bundled node_modules
node .runtime/phase1b-review-browser.cjs
```

命令退出 0，含明确 `finding: P2` 的观察结果；**这不是“所有需求通过”的断言**。本地上传 → 转写失败 → 缓存重试 → 草案 → 文字引用可用，R1 已复现。平台分享文案 → 规范化第2P来源 → 音频播放器 → 实际播放可用；390px视口无横向溢出，0个页面脚本错误。桌面/手机截图及ARIA快照在 `output/playwright/phase1b-review-browser/`，日志 `.runtime/phase1b-review-browser.log`。

## 需求与安全边界核对

- 整段文本与单视频URL入口、短链、B站分P、不同链接拒绝已有代码及测试支撑。输入校验发生在创建资料之前，不在请求线程联网。
- 下载不依赖ASR或AI，成功后明确等待手动转写；失败转写不重新下载，不覆盖已有校对原文。活跃任务唯一索引和编辑保护保留。
- 平台媒体保留来源与实际标题/时长；音轨使用音频控件。R1 是本地/历史媒体类型与播放的缺口。
- 单任务大小、时长、下载进程超时约束保留；测试覆盖声明/实际时长、大小和合集/直播拒绝。没有做长时间压力或总磁盘配额测试。失败片段可能保留的现有限制已在实现记录注明。
- 实际 `socket.connect/connect_ex` 地址检查与已校验IP固定逻辑仍在，不只检查最初URL；PyAV下载后探测限制为file协议。现有测试在本线程独立执行通过。此次不是完整SSRF对抗审计。
- 没有新增浏览器Cookie、平台密码、`.netrc`读取或登录绕过；yt-dlp配置显式禁用这些入口，没有引入 python-spider 旧代码或第三方签名服务。
- 原文校对、策略结构/引用校验、草案过期保护与导出主流程通过。真实ASR和真实LLM仍未验证。

## 真实平台证据（协调线程提供，未在本线程冒充复测）

已读取最新 `docs/phase-1b-network.md` 及协调机器可读结果：

- B站 `BV1bK411W797?p=2` 产品真实路径缓存 M4A 音频 2,170,299 字节，PyAV时长97.941111秒，状态待转写；Chrome播放时间前进约0.82秒，无ASR转写409。来源：`output/playwright/phase1b-live-result.json`。
- 用户实际抖音分享短链 `https://v.douyin.com/aU0BxZKBvVI/` 正确抽取，重定向可到视频页面；真实worker要求新的会话Cookie，返回安全平台限制、`has_media=false`、元数据为空。**未成功下载抖音媒体**，也不能把用户文案标题或网络页面200视为可信媒体元数据。来源：`output/playwright/phase1b-user-douyin-result.json` 及网络记录。
- 未下载模型、未运行真实语音识别或真实LLM提取。仅一个B站成功样例，不外推所有视频可用；抖音平台限制不能算下载成功。

## 本次审阅快照

以下SHA256对应本轮测试和发现；后续修复应有自己的定向复核记录：

| 文件 | SHA256 |
| --- | --- |
| app/main.py | `5560AEAC434A2407E80B6A8D26B971C22815FA7EF19C984C54CC840DC66CE252` |
| app/store.py | `141CEBE2EC06CAD750A84D63FB482DE692845850F4A8B26F31669B429C101C8E` |
| app/jobs.py | `B18798C71C0F5358012C17E4DF34E278071A664D9F5C3821C60B0D60342E895C` |
| app/adapters/download.py | `3DB2BE99B3D4831A1DBB3073B67942A056CE9A4724219B6D6AF11A6BF55E9493` |
| frontend/app.js | `928D7847223B762B1E793D17E8D9530CCC8C1AEF984E0C94F93FC997251CD712` |

验收线程状态：完成发现与证据记录，后续修复交协调线程安排；未自行修复产品或创建新线程。
