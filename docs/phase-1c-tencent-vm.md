# 腾讯云试用 Ubuntu VM：首次私有获取验证

2026-11-09。用户已选择腾讯云一个月试用；目前未创建实例、未收到云端运行证据。本文是执行准备，不是部署成功记录。通用包和参数以 [验证runbook](phase-1c-runbook.md) 为准，活动资格与费用研究由主聊天记录在 `research/free-cloud-options.md`。

## 领取与访问

在[腾讯云官方免费体验馆](https://cloud.tencent.com/act/pro/free)由用户本人完成账户操作，确认实际订单为0元、试用时长、实例规格、地区及到期处理；活动资格以该账户领取页为准。一个月试用不等于永久免费，本项目不会自动购买、续费或扩容。

选择受支持的Ubuntu镜像；实际运行解释器需Python 3.11或更高。记录实例地区、Ubuntu版本、CPU/内存/磁盘规格，用不含密钥和公网IP的环境说明作为后续证据。平台页面显示的配置不等于已验证的ASR性能。

这次只执行私有CLI，不启动FastAPI、uvicorn或8765服务，不需要开放80、443、8765等Web端口。可使用平台控制台登录；若使用SSH/SCP，22端口只对自己的当前公网IP放行，用独立密钥或平台提供的登录方式。密钥、密码和控制台登录会话不写入仓库、报告或聊天。

## 上传之前

1. 在本机按runbook生成白名单验证包，保留该包SHA256；检查包清单。
2. 只上传该包，不上传整份quant目录。正式data、个人文件、`.env`、`.venv`、`.runtime`及output均不应进入包。
3. 在云端普通用户的专用目录解包，校验SHA256与本机一致。若通过SCP上传，用实例控制台给出的实际用户名和地址；不要把文档中的占位符当成真实凭据。

## Ubuntu基础准备

以下命令只供实例创建后在云端执行；本阶段未执行这些安装。先确认磁盘空间与Python版本。系统包安装需该实例的sudo权限。

```sh
uname -sr
python3 --version
df -h .
free -m
sudo apt-get update
sudo apt-get install -y python3-venv unzip ca-certificates
```

若系统Python低于3.11，选择支持所需版本的Ubuntu镜像或按runbook的容器方案运行，不把本机Windows虚拟环境复制过去。下载验证只安装独立下载依赖；无需faster-whisper、模型权重、Ollama或AI密钥。

## 首轮执行与证据

使用runbook的Linux VM命令，在解包目录创建新的虚拟环境，安装包内`requirements-media-fetch.txt`，先运行CLI `--help`，再执行默认两个样本。保持串行、默认限制，不加入个人Cookie或代理规避平台验证；不要为追求抖音成功反复重试。运行环境选择必须明确为实际腾讯云VM，并用OS、区域/规格和上传包校验值作补充说明；单独一个自填cloud标签不能证明云端实测。

在解包后的目录执行（`.runtime/phase1c-tencent-first` 必须尚不存在；再次实验要使用新的名称，不能覆盖前次证据）：

```sh
python3 -m venv .venv-fetch
.venv-fetch/bin/python -m pip install --only-binary=:all: -r requirements-media-fetch.txt
.venv-fetch/bin/python scripts/validate_media_fetch.py --help
.venv-fetch/bin/python scripts/validate_media_fetch.py --label cloud --output-dir .runtime/phase1c-tencent-first
fetch_status=$?
printf 'fetch_exit_code=%s\n' "$fetch_status"
cat .runtime/phase1c-tencent-first/report.json
```

若依赖安装失败，先记录该环境问题，不继续把缺依赖结果当平台获取失败。CLI退出码0表示本次全部媒体成功；1表示存在失败或未运行条目，仍须读取报告；2表示输入/配置问题。`cloud_execution_verified`字段保持false是有意设计：工具不自行证明云环境，最终由真实实例记录与回传证据完成核验。不要手工把字段改成true来补足证据。

首轮只接收以下结果作为有效证据：

- CLI退出码、生成报告路径和完整计数，实际UTC开始/结束时间。
- 每个样本规范化来源、成功/失败、安全失败类别；成功时必须有实际媒体字节、时长和音频/视频类型。
- Python、yt-dlp、PyAV版本；用户确认的腾讯云区域与规格；真实Linux系统信息；包SHA256。
- 如果平台限制、DNS/网络失败、依赖安装失败、内存不足或超时，保留相应事实，不把网页200或短链跳转当成功，不把失败改写为用户Cookie过期。

报告回收后对照本机报告，才能回答“这一个云端出口是否可以获取这两个样本”。这不构成全平台成功率结论。只回传脱敏报告与必要环境说明；媒体文件可以留在试用机器上做本地探测，无需上传到聊天或公开文件服务。

## 收尾与下一步

报告回收并核对后，按runbook确认仅测试子进程已退出，按明确路径清理本次临时媒体或删除测试实例；不要误删仍需保留的结果。到期之前由用户确认续用或释放，检查磁盘、快照、流量等是否仍可能保留或产生费用。

即使验证成功，当前应用也尚未具备多用户公网服务条件。移动网页上线工作见 [迁移差距清单](phase-1c-cloud-gaps.md)；真实ASR和AI仍须单独配置与验收。
