# Phase 1C — 独立基本验收

日期：2026-11-09（Asia/Shanghai）。验收聊天 `01a1c03d-0b12-7e53-a625-433ec47012fa`；实现聊天 `01a1c038-2d64-7160-a9b1-691c1b26fd02`。目录 `C:/Users/Admin/Desktop/quant`，无 Git、分支或独立 worktree。

## 结论与接受范围

**通用 VM/容器源码准备包的基本验收通过，未发现必须修复的产品问题。** 独立运行全部 **115 项测试通过，0 失败**；另完成 **10 组离线检查（14 个 CLI 场景）**、空环境依赖缺失检查、白名单包校验及现存真实媒体重新探测。可以交协调接收本阶段准备成果；这不表示云端获取、Docker 构建、Linux 分支或完整应用上线已经通过。

新建最小环境从 PyPI 安装时，PyAV wheel 下载中途读取超时，**全新联网安装未通过验证**。随后仅复制本机已安装的两个锁定版本分发包到该空 venv，验证独立 ZIP 的 CLI/worker/PyAV 可运行；没有将这种离线复用记为安装成功。此为安装网络证据缺口，未观察到依赖版本或运行代码错误。

本轮是需求、主要流程和明显回归检查，**不是对抗审计**。通过 `wait_threads` 持续使用游标等待，确认实现 turn 于 20:36:24（Asia/Shanghai）完成后才读取最终实现并运行验收。未修改产品、原测试、正式 `data/`，未操作8765、浏览器或外部部署；只写本报告和独立 `.runtime/phase1c-review-*` 证据。没有重抓抖音或重复网络样本。

## 需求核对

| 验收项 | 结果与证据 |
| --- | --- |
| 单链接、完整分享文案、小 manifest、默认样本 | CLI 支持三种方式；默认与示例 manifest 一致，为用户抖音短链 `https://v.douyin.com/aU0BxZKBvVI/` 和 B站 `BV1bK411W797?p=2`。分享追踪参数去除，第2P保留；任意额外 manifest 字段使该项无效，不透传原文。独立单条及混合 manifest 检查通过 |
| 串行和完整计数 | `run_batch` 同步等待每个 `run_sample`，并发固定1。混合3项计数为尝试2/成功2/失败1；7项超量整批不启动下载，保留6个not_run与1个无效failed。无静默截断、去重或把未运行算成功 |
| 损坏/空/超字节 manifest | 现有新增测试覆盖损坏、错误形状、空数组、超过64 KiB；独立损坏输入退出2，`input_count_known=false`、`invalid_manifest`。无法枚举时total=0不冒充已处理；空数组数量已知但仍无效 |
| 默认与硬限制 | 默认32 MiB/600秒媒体/120秒任务/600秒批次，硬上限64 MiB/1200/300/900；最多5条。CLI独立检查65 MiB、1201秒、301秒、901秒、NaN均退出2。真实WAV超过实际时长/大小限制分别返回duration_limit/size_limit |
| 任务与批次超时 | 独立真实worker与其子进程在0.8秒任务/批次上限下终止；等待2.2秒后没有child-lived标记，并确认worker-started曾产生。整批3条：尝试1/失败1/未运行2，均明确batch_timeout。全套测试另覆盖Windows Job Object父子进程清理；Linux进程组分支未实跑 |
| 实际媒体与HTTP200区分 | 真实2秒WAV报告32044字节、audio、has_audio=true，覆盖夹带错误的平台声明；写有HTTP200的HTML伪装成WAV被标记invalid_media。不能只靠页面、元数据或状态码成功 |
| 报告与错误 | 报告含schema、UTC时间、OS/Python/两项依赖版本、标签、来源、attempted、状态/固定类别、耗时、实际媒体指标和完整计数。离线测试注入的原文、标题、token、签名CDN URL不出现在stdout/stderr/report；成功/失败都删除临时请求响应，失败媒体目录清除 |
| 云标签 | `--label cloud`仍报告真实Windows系统且`cloud_execution_verified=false`，不会把操作员标签当作云实测 |
| 复用下载器及凭据边界 | 独立worker调用生产`download_in_worker`；保留实际socket connect/connect_ex、重定向/CDN地址检查和解析地址固定。PyAV只允许file协议。yt-dlp显式禁用浏览器cookies、cookiefile、netrc、代理和缓存；worker环境白名单且HOME隔离。不导入app.config、dotenv、ASR或app.main，不加载模型 |
| 回归 | 全套115项通过，其中原有78、新增37。覆盖原有文本/字幕、校对/导出、缓存转写/失败重试、旧库迁移、本地音视频识别及实际连接检查。未在本轮重新做浏览器验收，阶段实现没有前端改动 |
| 独立包 | ZIP严格14成员；逐成员SHA256、总SHA256和允许清单通过。无data、.env、.runtime、output、.venv、媒体、模型或个人文件。实际解压包可异地运行，不依赖完整应用源码 |
| 容器/VM说明 | Dockerfile精确COPY、非root、无EXPOSE；文档只用解压白名单包作为context，不挂HOME/凭据/data，不映射端口。提供CPU/内存/PID约束和费用/存储边界。Docker daemon不可用已明确写为未构建、未运行；此次只完成静态核对 |

## 独立运行命令与结果

### 完整回归

为避免子进程写入原工作目录的pycache或默认数据，先将待验收源码、前端、测试、部署脚本及必要文档复制到自己的证据快照。没有复制data、运行结果或个人配置。快照41个源文件的SHA256保存在 `.runtime/phase1c-review-evidence/source-sha256.json`。

准备脚本：`.runtime/phase1c-review-prepare.py`。在该快照目录运行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
# cwd: C:/Users/Admin/Desktop/quant/.runtime/phase1c-review-evidence/snapshot
& 'C:/Users/Admin/Desktop/quant/.venv/Scripts/python.exe' -B -m pytest -q --basetemp='C:/Users/Admin/Desktop/quant/.runtime/phase1c-review-evidence/pytest-tmp' -p no:cacheprovider
```

**115 passed in 16.50s，退出0**。日志和退出码：`.runtime/phase1c-review-evidence/pytest.log`、`pytest-exit.txt`。测试产生的文件均在验收证据目录中。

### 最小运行依赖与独立CLI

```powershell
.venv/Scripts/python.exe -B -m venv .runtime/phase1c-review-evidence/minimal-venv
.runtime/phase1c-review-evidence/minimal-venv/Scripts/python.exe -I scripts/validate_media_fetch.py --output-dir .runtime/phase1c-review-missing-deps
.runtime/phase1c-review-evidence/minimal-venv/Scripts/python.exe -I -m pip --isolated install --disable-pip-version-check -r requirements-media-fetch.txt
```

- 空环境实际CLI退出1；默认两项均`not_run/dependency_missing`，attempted=0，total=2，未联网获取媒体。报告：`.runtime/phase1c-review-missing-deps/report.json`。
- pip退出2：已获得版本元数据，但PyAV 28.2 MB wheel下载到约10 MB时`files.pythonhosted.org`读取超时。原始日志：`minimal-install.log`，退出码：`minimal-install-exit.txt`。没有反复重试安装或将其视为产品通过证据。
- 离线补充使用 `.runtime/phase1c-review-local-deps.py`，仅从现有venv复制`yt-dlp==2026.10.26`与`av==19.0.2`分发包及其DLL/metadata到新venv；没有复制其他应用依赖。证据：`local-deps-fallback.json`、`minimal-installed.json`。该venv仅有pip和两项运行依赖，无FastAPI、dotenv、faster-whisper或pytest；实际导入yt_dlp和av成功。

```powershell
.venv/Scripts/python.exe -B .runtime/phase1c-review-local-deps.py
.runtime/phase1c-review-evidence/minimal-venv/Scripts/python.exe -I .runtime/phase1c-review-checks.py
```

**退出0，10组检查通过（9个CLI输入场景，加1组5种硬限制拒绝），另核实真实平台媒体文件。** 明细为 `.runtime/phase1c-review-evidence/independent-results.json`，运行日志/退出码为`independent-checks.log`、`independent-checks-exit.txt`。每场景报告位于同目录`phase1c-*`子目录，控制台记录为`*-console.json`。

边界说明：`.runtime/phase1c-review-fixture-cli.py`从实际解压包加载CLI并执行实际`main`；仅把下载边界替换为明确的离线测试WAV/HTML/睡眠worker，保留实际子进程、Windows Job Object、环境隔离、PyAV探测、返回值过滤和报告路径。这证明入口与资源控制/媒体检查，不证明第三方网络下载成功。生产下载器本身由全套测试及下述既有真实样本支撑。

脚本复跑时需使用新的证据输出目录，CLI按设计拒绝覆盖已存在目录；不得为复跑删除不属于本验收的文件。

## 本次平台证据复核

读取实现生成的 `.runtime/phase1c-local-real-20261109/report.json` 和退出码文件，不重新请求平台。其实际网络执行为2026-11-09 20:22:45—20:22:53（Asia/Shanghai），总2/尝试2/成功1/失败1/未运行0，退出1。两个样本各启动过一次真实worker。

- **B站第2P：** 本验收用最小环境重新打开现存`sample-002/media/source.m4a`，得到 **2,170,299字节、97.941111秒、1音轨/0视频轨**，并成功解码第一帧1024个音频样本，与报告一致。SHA256：`c28a3156367a622c9ebd377842b7815f23332526f1d5e7bd9edad898209c4e6e`。独立证据：`.runtime/phase1c-review-evidence/real-media-check.json`。
- **用户抖音短链：** 原报告`failed/platform_restricted`、media=null，无真实时长、体积或平台标题；不能说已取得媒体，不能推断用户Cookie过期或云端必然能解决。
- 这份真实网络报告早于最终增加`input_count_known`字段的离线修改，未含该字段；实现交接已明确注明。原报告total=2可由默认输入与两行结果核对，未改写旧证据。最终字段由本验收的新报告和完整测试验证。

## 包快照与协调交接注意

已验收ZIP：`.runtime/phase1c-package-final/media-fetch-validation.zip`。

总SHA256：`3f99d5816b5686b9fa6fb6456ee76bac5b9750768d258722f5e987b55497f589`；14成员、成员清单覆盖其余13文件，逐项校验通过。证据：`.runtime/phase1c-review-evidence/bundle-check.json`。

**无必须创建产品修复聊天的发现。** 核对包与当前目录时只有`docs/phase-1c-runbook.md`不同：协调在实现收尾后加入腾讯云Ubuntu私有CLI说明，包中的原版通用VM/容器说明仍完整。精确差异保存于`bundle-source-diff.txt`。这是已授权的文档补充，不是程序或打包白名单故障；若最终交付希望包内也带新说明，协调应重新生成包并核对新SHA256，不能沿用本报告旧包哈希。腾讯云专门说明按任务约定由协调单独校核。

## 尚未验证

- 真实Linux VM/云端获取、Linux进程组/SIGTERM分支、其他架构或Python3.11的wheel安装兼容性。
- Docker镜像构建和容器运行。已读取实现`phase1c-docker-status.json`：客户端存在、daemon不可用、image_built=false、container_run=false；未启动Docker Desktop或变更用户环境。
- 全新联网依赖安装成功：本轮PyPI下载超时，仅完成隔离最小依赖运行验证。
- 真实ASR、AI、手机/App分享、公开HTTP服务、多用户身份隔离与完整产品云迁移；这些不属于本阶段准备包验收。
- 大规模成功率、长期容量/内存压力、所有平台视频可用性；单个B站成功不作外推。

验收状态：**基本验收完成，可接收准备包；上述云端/安装证据边界保留。** 未自行修改产品或创建修复聊天，交协调更新阶段索引与最终接受状态。
