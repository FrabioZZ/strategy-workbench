# Phase 1 补充修复：本地 ASR 配置与真实转写

日期：2026-11-10（Asia/Shanghai）。本可见实现聊天负责模型与转写；下载修复由另一可见聊天处理，正式部署与独立基本验收由协调聊天处理。共享目录 `C:/Users/Admin/Desktop/quant`，非 Git 仓库，无分支或新 worktree。

## 实现结论

本工作流已完成：官方模型、兼容依赖和本地配置就绪；两条真实模型执行路径通过，文本/时间戳/缓存/持久化检查通过。等待协调工作流完成新平台素材的集成验收与正式服务重启。本轮未做对抗审计。

- 官方 `Systran/faster-whisper-small` 已下载到 `data/models/faster-whisper-small`；固定 commit `536b0662742c02347bc0e980a01041f333bce120`。
- 权重 `model.bin` 483,546,902 字节，SHA256 `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`。完整清单见 [.runtime/phase1-asr-model-manifest.json](../.runtime/phase1-asr-model-manifest.json)。下载显式 `token=False`，未读取 HF 凭据、未修改系统网络；下载与校验共33.406秒。
- 已真实离线加载：`cpu`、请求 `int8`、实际 CTranslate2 `int8_float32`。加载3.546秒，含导入5.687秒；进程峰值工作集729,452,544字节。详见 [加载报告](../.runtime/phase1-asr-load.json)。
- `.env` 仅更新三个 ASR 字段：`ASR_MODEL_PATH` 绝对路径、`ASR_DEVICE=cpu`、`ASR_COMPUTE_TYPE=int8`。没有修改其他字段。
- 中文合成样本的隔离上传/自动转写、真实旧B站音轨的上传/重启/手动缓存转写均成功（见下）。本轮不代表两平台链接导入或真人中文教学准确率已集成验收。

## 已修复的依赖故障

首次真实上传和手动缓存转写均失败；直接调用 ASR 取得原始异常：`faster_whisper/audio.py:46` 调用 `av.open(..., metadata_errors="ignore")`，PyAV19.0.2拒绝该参数，抛出 TypeError。不是模型下载损坏，也没有进入推理。新增 `tests/test_asr_runtime.py` 以真实1秒PCM文件复现同一异常，首次结果1 failed。

为固定这一ASR运行条件，本轮已同步限定 `requirements.txt` 中的PyAV兼容版本，并更新 `requirements-lock.txt` 的av版本；这是必要依赖修正，未改下载器、网络模块、`app/config.py`或`app/jobs.py`。正式服务仍未重启。

已安装 PyAV18.1.0；同一真实PCM测试由1 failed转为1 passed（1.25秒）。`requirements.txt`新增`av>=11,<19`，锁文件仅将av改为18.1.0。[上游PyAV19发布说明](https://github.com/PyAV-Org/PyAV/releases/tag/v19.0.0)确认删除了该参数；本机原始堆栈与说明一致。首次pip轮子下载停滞后有界停止，改用httpx从PyPI官方`files.pythonhosted.org`下载27,595,679字节轮子并核对PyPI SHA256 `ea1480b7a8d5405cb5f382b344731bf125fd2c1c6fae3964f6c48595628387ff`，然后无网络安装；未修改pip/系统/个人配置。

## 真实模型推理：已知中文合成样本

音频是**本机合成语音，不是真人教学录音**：Microsoft Huihui Desktop，默认语速，用Windows已安装的System.Speech离线生成；沙盒无法调用语音引擎后，仅该生成操作通过授权宿主执行。未使用远程TTS。原音频与已知文本分别保存于 [.runtime/phase1-asr-fixtures/synthetic-zh-huihui.wav](../.runtime/phase1-asr-fixtures/synthetic-zh-huihui.wav) 和 [原文](../.runtime/phase1-asr-fixtures/synthetic-zh-huihui.txt)。音频15.399002秒、679,142字节，SHA256 `69ff02de64be667a04369cb75aca32fa9d6517fdec0a9c31c0964d45f36a0cde`。

使用生产`create_app`、上传路由、任务队列、独立媒体子进程和真实模型；没有ASR/下载/AI替身。`.runtime/phase1-asr-real-synthetic-zh-20261110-202142/data`隔离数据库。上传HTTP202后任务`succeeded`，从上传到完成18.203秒（含媒体探测、模型加载和推理）；三个原始输出段落如下，未人工改写识别结果：

| 起止秒 | 识别文本 |
| --- | --- |
| 0.00–2.50 | 这是本地语音转文字验证。 |
| 3.20–8.00 | 我们先导入音频,再检查转写段落和时间戳。 |
| 8.70–14.70 | 请记住,识别结果需要人工校队,不能直接作为交易指令。 |

对照已知原文发现“校对”误识为“校队”，其余正文一致（标点形式有差异）。这证明当前链路可用，不代表真人中文教学、证券术语或数字识别准确率已经全面验收。

已验证：文本非空；所有时间在源音频范围内；关闭并重新创建应用后段落完全保留；媒体GET为200且SHA256一致；再次转写HTTP409，已有内容不会覆盖。完整[报告](../.runtime/phase1-asr-real-synthetic-zh-20261110-202142/report.json)、可复跑[探针](../.runtime/phase1-asr-verify-real.py)。

资源采样：真实ASR子进程峰值工作集739,225,600字节（约705MiB），峰值采样私有提交3,425,845,248字节；累计CPU采样39.875秒（多线程CPU时间，不是墙钟时间）。Windows每0.2秒采样子孙进程，结束瞬间可能漏掉CPU尾部；私有提交与实际驻留内存不同，不应混称RAM用量。模型/依赖加载峰值计入进程峰值；这是单机单样本测量，非吞吐基准。

## 真实旧B站缓存：手动转写与保全

复用2026-11-09已下载的 `.runtime/phase1c-local-real-20261109/sample-002/media/source.m4a`，97.941111秒、2,170,299字节、SHA256 `c28a3156367a622c9ebd377842b7815f23332526f1d5e7bd9edad898209c4e6e`。先以未配置ASR的隔离应用上传（HTTP202，无自动任务），关闭该应用，再以真实模型配置重启同一隔离资料库，调用`POST /api/documents/{id}/transcribe`（HTTP202）。

任务真实执行并`succeeded`，墙钟93.844秒（含冷加载），56个非空段落，时间范围0.14–94.44秒，均在源音轨内。关闭并再次创建应用后转写完整保留，重复转写409，媒体GET200且哈希一致。峰值工作集739,434,496字节，峰值采样私有提交3,537,514,496字节，累计CPU采样315.625秒。

这是**历史缓存的执行流程证据，不是本次平台下载成功证据，也不是中文教学准确率验收**。探针标签沿用了`cached-bilibili-music`，该标签不代表已人工听辨内容。产品固定`language="zh"`，输出中有反复或可疑的转写，不能仅因返回中文就认定原声为中文或识别准确。完整原始段落/时间戳保存在[报告](../.runtime/phase1-asr-real-cached-bilibili-music-20261110-202214/report.json)，未润色或用样例文本替换。

额外以同一真实模型做自动语言检测（未改产品设置），结果为`ja`，概率0.993675；见[检测结果](../.runtime/phase1-asr-cached-language.json)。这是模型判断而非人工听辨，但足以说明旧样例不适合当中文教学识别质量证据。后续集成验收应使用协调聊天选择的中文口述B站或用户抖音教学素材；本轮已知中文合成样本只证明有参考原文的基础识别可运行。

首次失败报告也保留：[中文样本（PyAV19）](../.runtime/phase1-asr-real-synthetic-zh-20261110-201604/report.json)、[旧B站缓存（PyAV19）](../.runtime/phase1-asr-real-cached-bilibili-music-20261110-201625/report.json)。两个失败任务均保留媒体。早期探针在失败后发起了额外的“重复转写”请求，退出应用时该请求被中断；成功版探针只对已生成文本的任务检查409，避免将失败重试混入验收。

## 部署边界

本聊天不停止/重启正式8765服务，不修改正式数据库。正式进程需由协调聊天安排重启读取 `.env`；`asr_configured=true` 仅说明模型权重文件存在，最终以真实任务成功为准。当前未修改 `app/config.py`、`app/jobs.py`、ASR适配器或模型下载产品脚本。

生效条件：使用本项目`.venv`，faster-whisper1.2.1/CTranslate2 4.8.5/PyAV18.1.0；`.env`的模型绝对目录为`C:/Users/Admin/Desktop/quant/data/models/faster-whisper-small`，设备cpu、计算类型int8。新进程读取配置后可自动转写新上传文件；已有缓存走手动转写。无需HF账号、GPU、独立FFmpeg或远程ASR服务。每个任务仍独立加载模型，长音频受既有1小时子进程超时与文件限制约束；本次隔离探针设600秒上限。

## 回归与改动清单

2026-11-10完整回归命令：

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/phase1-asr-full-suite -p no:cacheprovider --tb=short
.venv/Scripts/python.exe -m pip check
```

结果：**229 passed，58.36秒，退出0**；104条告警来自Backtrader使用`datetime.utcnow()`的弃用提示，无测试失败。`pip check`为`No broken requirements found`。这些单元/回归测试不代替上述真实模型探针；真实模型探针两个成功运行均退出0。

本工作流修改：

- `.env`：仅三个ASR字段。
- `requirements.txt`、`requirements-lock.txt`：兼容PyAV范围与实测锁定版本。
- `tests/test_asr_runtime.py`：无需权重的真实PCM解码回归，已先失败后通过。
- `README.md`：仅ASR段落，说明保留已有配置、兼容版本与重启/使用路径。
- 本记录，以及`data/models/faster-whisper-small/`、本记录链接的`.runtime`隔离证据/探针/样本。

重新验证可用以下命令（每次生成新的隔离数据目录）：

```powershell
.venv/Scripts/python.exe .runtime/phase1-asr-verify-real.py --sample .runtime/phase1-asr-fixtures/synthetic-zh-huihui.wav --label synthetic-zh
.venv/Scripts/python.exe .runtime/phase1-asr-verify-real.py --sample .runtime/phase1c-local-real-20261109/sample-002/media/source.m4a --label cached-bilibili-music --manual
```

协调工作流准备好新的中文媒体后，可将`--sample`替换为对应本地文件，设置明确的`--label`，再以相同生产路由独立复验。旧B站样例的自动检测语言为日语，不应作为中文教学准确率的接受依据。
