# Phase 1B — R1 媒体播放回归修复

日期：2026-11-09（Asia/Shanghai）。可见修复聊天：`01a1bf56-3412-76e3-b7d6-7de314cd1896`。工作目录 `C:/Users/Admin/Desktop/quant`；共享目录，非Git，无branch/worktree。范围仅处理独立基本验收的R1，没有扩张非阻塞建议、Cookie/会话功能或真实下载验证。

## 交接与结果

先通过 `wait_threads` 等待验收聊天 `01a1bf3f-b0f0-7c50-89e3-36e8ac477f10` 返回完成，再读取 `docs/phase-1b-review.md` 后修改产品。最终报告仅一项P2回归。现已完成必要修复及基本复核，R1复核标准通过；阶段整体接受及正式服务更新交协调线程处理。原验收报告不作改写。

## 修复前复现

验收已在浏览器确认：有效3秒WAV上传后 `has_media=true`、`media_metadata={}`，转写后仍无 `#media-player`；证据只聚焦文字，不能定位媒体。本线程新增 `tests/test_local_media.py` 后、修改产品之前运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe -m pytest tests/test_local_media.py -q --basetemp=.runtime/phase1b-fix-red -p no:cacheprovider --tb=short
```

**9 failed in 4.95s**，均在预期元数据断言失败，实际元数据为空。包括真实WAV、错误后缀WAV、静音视频、旧库、探测失败及网络引用回退。测试不加载模型、不下载平台素材。

根因：上传只保存文件路径，旧库新增列默认为空对象；前端只根据真实类型创建audio/video。恢复应补齐后端元数据，不能用后缀把音轨当作视频。

## 实现

- `app/main.py`：本地媒体上传完成后调用受控本地探测，无ASR仍只缓存；详情GET对缺少类型的历史缓存按需恢复。上传等待在线程池中运行，不在事件循环/主进程中打开PyAV。
- `app/jobs.py`、`app/media_worker.py`：复用现有worker执行`probe`，单次最多30秒且不超过原任务时限，超时终止并回收子进程。校验文件在当前数据目录内、存在且大小合规；PyAV仅使用file协议白名单并检查实际时长。探测串行，成功/失败结果持久化，避免刷新反复启动子进程。探测不创建或覆盖用户下载/转写任务。
- `app/adapters/download.py`：复用真实容器/轨道检查。默认下载检查仍要求音轨；仅本地探测允许静音视频，并记录`has_audio=false`。类型依据流信息，不依据后缀。下载调用、真实connect/connect_ex地址检查和DNS固定代码未改动。
- `app/store.py`：补充操作只更新`media_metadata`列并核对当前媒体路径；保留已有平台字段，不修改资料标题、时间、原文、revision、草案或任务。旧库仍用原有加列迁移，不删除或重建用户数据。
- `frontend/app.js`：既有audio/video分支获得真实类型后自然恢复播放器及证据跳转；无法探测时明确提示保存到本地播放器或转换重传，缓存字节保留。
- `tests/test_local_media.py`新增9项；`tests/ui_server.py`只为测试提供有效媒体/旧数据fixture，`probe`仍调用真实生产worker，下载/ASR/提取继续使用显式替身；`scripts/ui_smoke.cjs`扩展浏览器复核。README/VERIFICATION仅补本次修复说明。

## 验证与证据

| 检查 | 结果 |
| --- | --- |
| 定向红绿测试 | 修复前9 failed；修复后9 passed in 12.71s |
| 全项目pytest | **78 passed in 21.30s**，退出0；原有69项加9项回归 |
| JS语法 | `node --check frontend/app.js`、`node --check scripts/ui_smoke.cjs`，退出0 |
| 真实上传与类型 | 3秒WAV读取成功；改为`.mp4`后缀仍是audio；静音3秒H.264为video，真实has_audio=false |
| 旧库无损恢复 | 从无media_metadata列的旧库迁移；原资料列、所有草案/任务逐行不变，revision=2、草案有效、导出引用时间=1秒；重新启动复用已保存元数据 |
| 失败回退 | 损坏文件、时长超限、旧文件大小超限、worker超时均保留缓存；重复GET不反复探测 |
| 网络边界 | 上传包含HTTP引用的伪WAV，真实子进程PyAV拒绝，监听器收到0个请求；主进程探测调用被测试禁止；原下载/实际connect/connect_ex测试通过 |
| Chrome本地播放 | WAV实际currentTime=0.215660、视频=0.212700、历史WAV=0.210187（均从0前进）；历史草案证据跳至第1秒并聚焦相应原文 |
| Chrome保留与回退 | 历史title/revision/segments/strategy/strategy_revision/strategy_stale/jobs/created_at/updated_at一致；无效文件无虚假播放器、下载字节保持原样 |
| Chrome既有流程 | 分享文案/多链接拒绝/B站分P、无ASR缓存、模拟转写失败与缓存重试、提取、编辑、导出、过期保护、刷新及390px布局全部通过，0个页面脚本错误 |

完整命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1b-fix-full -p no:cacheprovider --tb=short
# NODE_PATH指向load_workspace_dependencies返回的bundled node_modules
$env:PLAYWRIGHT_CHANNEL='chrome'
node scripts/ui_smoke.cjs
```

浏览器脚本启动前检查8766空闲，启动并在结束后关闭自己的服务；隔离数据目录 `.runtime/ui-1794211960314`。第一次浏览器执行在点击历史资料后立即断言、未等待异步渲染，失败于播放器数量；增加按标题等待后完整通过，产品逻辑未因此变更。

日志：`.runtime/phase1b-fix-pytest.log`、`.runtime/phase1b-fix-browser.log`。结构化结果：`output/playwright/phase1b-fix-result.json`。截图：`phase1b-fix-local-audio.png`、`phase1b-fix-local-video.png`、`phase1b-fix-legacy-citation.png`、`phase1b-fix-mobile-audio.png`，均位于`output/playwright/`。

## 局限与交付边界

类型/时长探测不证明所有编码均可在浏览器播放；已实测WAV PCM与H.264。无法探测、超限或超时的文件保留缓存，失败标记避免每次打开重复工作；当前没有单独“重新探测”按钮，可本地打开或转换重传，原资料仍保留。首次打开旧媒体需等待探测，单次子进程有30秒上限；并发探测会排队。

下载/ASR/LLM成功流程在本次测试中均为明确替身；未下载模型、配置真实模型或重跑真实平台下载。协调线程的真实网络事实不变：B站第2P成功缓存M4A并Chrome播放；用户实际抖音短链能跳转但yt-dlp要求fresh cookies，未取得媒体，不能据此断言必须账户登录。

未改正式`data/`，未重启/操作8765，未使用8768/8769；未改阶段索引、网络报告、python-spider评估或原review结论。未创建新线程或后台代理。仅进行需求对齐、主流程与明显回归基本复核，未扩张为对抗审计。
