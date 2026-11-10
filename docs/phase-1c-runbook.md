# Phase 1C 服务端媒体获取验证包

此包用于小样本验证“服务器是否取得真实音视频”，不启动产品、不开放 HTTP 端口、不运行 ASR/AI，也不读取 `.env`、浏览器 Cookie、账户或外部签名服务。分享文案只是待解析数据。请仅使用有权处理的来源。

## 文件与入口

- 入口：`scripts/validate_media_fetch.py`；独立子进程复用 `app/adapters/download.py`，保留实际 socket 出站地址检查及 PyAV 仅本地文件协议探测。
- 轻量依赖：`requirements-media-fetch.txt`，只有固定版本 yt-dlp 与 PyAV，不安装项目完整依赖或模型。PyAV 的平台 wheel 自带媒体库；没有兼容 wheel 时安装可能失败，不在本阶段隐式安装编译工具或模型。
- 抖音另需 Node.js 20+、Google Chrome 和包根目录的 `npm ci --ignore-scripts`；Windows CLI 使用系统级 Chrome 安装。CLI 只把已发现的 Node 目录加入隔离 worker 的 PATH，保留 Windows 程序安装根目录，并创建本次运行自己的空 AppData 目录；不继承个人配置、代理、密钥、`NODE_PATH` 或 `NODE_OPTIONS`。项目使用自己的 `playwright-core`，无 Codex 运行库回退。B站不需要这些浏览器依赖。
- 默认输入与 `deploy/media-fetch/samples.json` 相同：用户抖音短链、B站 `BV1bK411W797?p=2`。
- 所有输出使用**新目录**，名称必须以 `phase1c-` 开头。默认自动生成 `.runtime/phase1c-fetch-UTC-随机值`；显式目录已存在会拒绝，避免覆盖证据。
- 报告在该目录 `report.json`；成功媒体在 `sample-NNN/media/source.*`。失败下载残片清除；Windows退出时文件句柄释放最多再等待2秒。若仍无法清除，报告明确记为`cleanup_error`，本次目录中的残片保留待检查，不冒充下载成功或无效参数。worker 输出丢弃，临时请求/响应文件删除。媒体不会自动上传或打包。

## Windows 本地

在项目根目录 PowerShell 中可用已有 `.venv`：

```powershell
.venv/Scripts/python.exe scripts/validate_media_fetch.py --output-dir .runtime/phase1c-my-local --label local
.venv/Scripts/python.exe scripts/validate_media_fetch.py '分享文案 https://v.douyin.com/aU0BxZKBvVI/' --output-dir .runtime/phase1c-single
.venv/Scripts/python.exe scripts/validate_media_fetch.py --manifest deploy/media-fetch/samples.json --output-dir .runtime/phase1c-manifest
```

同一次实验选一种输入方式；不要为了追求成功反复执行。完整分享文案应整体引号包裹；不建议在 shell 命令中输入任何秘密。可用 JSON manifest 避免分享文本进入 shell 历史。manifest 是 UTF-8（允许 BOM）的 JSON 数组，元素为字符串或仅包含 `source` 的对象；任意额外字段会使该项无效，不回显字段。输入为无效或重复视频也逐项计数，不自动去重。

在全新目录中创建轻量环境（不执行项目 setup、run 或模型下载脚本）：

```powershell
py -3.12 -m venv .runtime/phase1c-fetch-venv
.runtime/phase1c-fetch-venv/Scripts/python.exe -m pip install -r requirements-media-fetch.txt
.runtime/phase1c-fetch-venv/Scripts/python.exe scripts/validate_media_fetch.py --output-dir .runtime/phase1c-light-local
```

## 白名单包生成与传递

```powershell
.venv/Scripts/python.exe deploy/media-fetch/build_bundle.py --output-dir .runtime/phase1c-package-handoff
```

生成 `media-fetch-validation.zip`、`SHA256SUMS`、`bundle-manifest.json`。源码白名单在生成脚本的 `FILES`；固定 ZIP 时间戳与顺序使相同文件产生相同包哈希。包只带独立入口、Windows launcher、下载器和两个空/无副作用的包入口、依赖文件、测试、容器文件、示例与本说明。**没有** `data/`、`.env`、`.runtime/`、`output/`、`.venv/`、媒体、个人配置或完整项目拷贝。包内哈希清单覆盖除自身外的每个成员。

只传这三个生成文件到已授权 Linux VM。源包不是离线镜像或 wheel 集合；安装依赖与拉取镜像仍需网络。不要把整个当前工作目录作为 Docker context；只在解压后的白名单包根目录构建。根 `.dockerignore` 为默认拒绝、逐项放行。

## Linux VM（需要现有已授权环境）

以下假定已安装 Python 3.11+、venv、unzip；不创建或购买云资源：

```sh
sha256sum -c SHA256SUMS
unzip media-fetch-validation.zip -d phase1c-source
cd phase1c-source
python3 -m venv .runtime/phase1c-venv
.runtime/phase1c-venv/bin/python -m pip install -r requirements-media-fetch.txt
.runtime/phase1c-venv/bin/python scripts/validate_media_fetch.py --label linux-vm --output-dir .runtime/phase1c-vm-real
status=$?
printf 'validator_exit=%s\n' "$status"
cat .runtime/phase1c-vm-real/report.json
```

VM 建议单核、至少 1 GiB 可用内存及 1 GiB 可用磁盘作为小样本试验预算，实际 PyAV/依赖和镜像空间另计。CLI 本身不提供 VM 级内存或磁盘配额；共享环境用容器/系统配额约束。不要将此 CLI 接成没有用户隔离的公网 API。

## 腾讯云一个月试用：Ubuntu首次私有验证

用户已选择腾讯云一个月试用，实例尚未创建。由用户本人在官方账户确认订单0元、试用期限、地区/规格和到期处理；试用不等于永久免费。此次只运行CLI，不开放80、443或8765等Web端口。可用控制台登录；需要SSH/SCP时仅对自己的公网IP放行22端口，密钥与密码不进入项目或报告。

先按上节传递ZIP、SHA256SUMS和清单，核验哈希后解包；使用Python 3.11+的Ubuntu镜像。在云端需要时显式安装系统基础包，然后继续Linux VM步骤：

```sh
python3 --version
df -h .
free -m
sudo apt-get update
sudo apt-get install -y python3-venv unzip ca-certificates
```

虚拟环境创建及依赖安装成功后，首轮在解包根目录执行以下命令，使用新的结果目录：

```sh
.runtime/phase1c-venv/bin/python scripts/validate_media_fetch.py --label cloud --output-dir .runtime/phase1c-tencent-first
status=$?
printf 'validator_exit=%s\n' "$status"
cat .runtime/phase1c-tencent-first/report.json
```

首轮默认两样本、串行、各一次即可。回收退出码、报告、包SHA256和实例地区/规格/Ubuntu版本说明；不回传凭据，不更改`cloud_execution_verified=false`来补足证据。只有在真实实例运行并核对这些记录后，才能记为云端实测。下载验证不需要ASR/AI配置，也不证明试用实例能承载整个产品；完整迁移条件见原项目 `docs/phase-1c-cloud-gaps.md`。腾讯云准备详情见原项目 `docs/phase-1c-tencent-vm.md`（这两份协调文档不在独立包内）。

## Linux 容器（本机尚未构建、运行）

基础 Docker 镜像未安装 Node/Chrome；其中的抖音流程需要另行配置运行时和项目 npm 依赖。桌面 CLI 实测不代表容器或云端验收。

只在解压包根目录运行：

```sh
docker build -f deploy/media-fetch/Dockerfile -t phase1c-media-fetch:local .
mkdir -p .runtime/phase1c-container-results
docker run --rm --init --read-only --cpus=1 --memory=1g --pids-limit=64 \
  --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --mount "type=bind,src=$(pwd)/.runtime/phase1c-container-results,dst=/results" \
  phase1c-media-fetch:local --label container --output-dir /results/phase1c-real
status=$?
printf 'validator_exit=%s\n' "$status"
cat .runtime/phase1c-container-results/phase1c-real/report.json
```

容器不映射任何端口，不挂载宿主 HOME、Docker socket、`.env` 或应用 data。Dockerfile 默认非 root UID10001；示例运行命令使用当前用户 UID 以写入自己的结果目录。自定义 manifest 可单独只读挂载文件并传 `--manifest /input/samples.json`。绑定目录须由运行 UID 可写；不能靠挂载整个项目解决权限问题。

镜像基础标签未锁定 digest；这里交付可重复**源码 ZIP**，不宣称镜像逐字节可复现。云端未准备就绪时保留准备包即可，不启动循环或自动调度。

## 限制与退出码

| 项目 | 默认 | 允许的硬上限 |
| --- | --- | --- |
| 样本数 | 2 | 5；超量整批不运行，仍记录全部可解析条目 |
| 并发 | 1 | 固定1、串行 |
| 每样本媒体字节 | 32 MiB | `--max-mib` 64 MiB |
| 实际媒体时长 | 600 秒 | `--max-duration` 1200 秒 |
| 每样本任务时间 | 120 秒 | `--task-timeout` 300 秒 |
| 整批任务时间 | 600 秒 | `--batch-timeout` 900 秒 |
| manifest 大小 | — | 64 KiB，超限拒绝，不截取半份输入 |
| 每条文案长度 | — | 8192 字符，超限标记无效，不截断 |

可以降低参数，也可以在硬上限内提高；所有数值必须为正且有限。整批截止时当前 worker 被终止，剩余条目标记 `not_run/batch_timeout`。进程启动、退出清理与写报告有短暂开销；时限控制的是任务运行，不是对进程全部退出用时的实时系统保证。Windows 使用 kill-on-close Job Object 和启动握手；Linux 使用独立进程组，超时后杀整组。外部媒体下载程序未启用。

下载器保留已有连接重试策略（`retries=1`）；CLI 每条只启动一次 worker，且没有自动再跑失败样本。大小控制包含下载器预检、进度及父进程监控和最终文件检查；它不是精确网络流量账单配额，网页请求、重试、缓冲及依赖/镜像下载流量另计。最大五条成功文件累计不超过320 MiB；失败残片在本次目录内清除。没有创建计费资源或任何自动采购行为。

- `0`：所有输入取得并检查真实媒体。
- `1`：至少一条失败或未运行，包括平台限制、依赖缺失、样本过量；不是成功码。
- `2`：参数、manifest或新输出目录无效。不能解析/超限manifest时报告明确 `input_error`、`input_count_known=false`，总数0表示无法枚举输入，不能解释成“已验证0条成功”；空数组同样无效，但已知条目数为0，`input_count_known=true`。参数/输出目录错误仅输出固定安全JSON，不保证能落盘。
- `130`：在任务外收到用户中断；任务内中断会收尾并将本条失败/剩余未运行写入报告，返回1。

## 报告解释与证据回收

`schema_version=1`，时间使用UTC；运行标签仅允许 local/linux-vm/container/cloud/ci，与操作系统、Python及依赖版本分开记录。`cloud_execution_verified=false` 永远表示程序不能自动确认云资源来源，输入 `--label cloud` 不会提升证据。要宣称云端实测，人工附上实际执行平台/资源、操作者记录及 Linux 报告；不要回收密钥、连接串或实例凭据。

每项含规范化 `source`、可用时的 `resolved_source`、attempted、状态、固定 category、耗时；成功才含实际大小、时长、audio/video、has_audio、扩展名及相对文件位置。没有标题、分享原文、任意manifest字段、下载临时URL或原始异常。HTTP200、页面可跳转或仅取得元数据都不是成功。`summary.total = succeeded + failed + not_run`，attempted另计；无效项属于failed且没有启动worker。整批过量时有效项为not_run，无效项仍为failed。

主要失败类别：`platform_restricted`（平台提示权限/验证等，并不证明用户Cookie过期）、`network_error`、`unavailable`、`download_error`、`invalid_media`、`unsupported_media`、`size_limit`、`duration_limit`、`task_timeout`、`batch_timeout`、`dependency_missing`、`worker_error`、`invalid_input`、`sample_limit`、`interrupted`。worker_error包含无法建立隔离或异常退出，不打印底层异常。

回收该次 `report.json`、CLI退出码、源码包SHA256、人工执行环境记录即可；媒体仅在有权共享且确实需要时另行传递。抖音失败时停止该样本，不导入浏览器凭据、签名/付费解析，也不因云部署而预先承诺可用。建议用户有权取得的文件上传作为后续产品回退。

## 离线回归

原项目已有pytest可直接运行；在独立轻量环境验证时先显式安装 `pytest>=8,<10`，它不是运行依赖：

```sh
python -m pip install 'pytest>=8,<10'
python -m pytest tests/test_media_fetch_validation.py -q --basetemp=.runtime/phase1c-tests -p no:cacheprovider
```

测试不访问真实平台；覆盖真实WAV探测、网页非媒体、大小/时长、报告计数和脱敏、依赖缺失、真实超时进程树、打包白名单及解压后独立入口。原项目全套回归仍需原项目完整依赖，不属于轻量包运行要求。

Windows进程树策略依据：[Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。本阶段本机实测记录与未验证项见原项目 `docs/phase-1c-implementation.md`，该交接文档不装入独立源码包。
