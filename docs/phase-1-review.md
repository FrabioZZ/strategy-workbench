# Phase 1 后端基本验收

日期：2026-11-09（Asia/Shanghai）  
可见聊天：Phase 1 - 视频转策略基本验收；`01a1bedf-15e2-70c2-953b-2698756bc8b6`  
目录：`C:/Users/Admin/Desktop/quant`；非 Git 仓库，无分支。  
范围：需求对齐、后端主流程及明显回归；未进行对抗审计。没有修改产品代码或现有测试。

## 结论

**有条件接受（后端范围）**。25 项现有测试、8 组独立补充检查通过。未发现阻断导入、校对、后台处理、失败重试、持久化和策略导出的后端缺陷。一项非主流程的 API 文档页面缺陷需修正，见 R1。前端/浏览器主流程由协调聊天另行验收，本报告不替代该结论。

用户已明确暂时没有 AI，先完成可运行界面和接口。本机未配置 ASR 模型及 AI 提供方，因此真实 ASR、真实平台下载、真实 LLM 成功不作为本轮通过条件，也没有声称它们已通过。没有下载模型或访问外部模型服务。

## 发现

### R1 — P2，非主流程阻断：API 文档页面与 CSP 冲突

- 位置：`app/main.py` 的 `FastAPI(... docs_url="/api/docs" ...)` 配置和 `local_security` 中的 `Content-Security-Policy` 响应头设置（审查时分别为第 57、74 行，以当前文件为准）。
- 请求 `GET /api/docs` 得到 200，但 HTML 引用 `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js` 和同域 CSS，并通过内联 `<script>` 调用 `SwaggerUIBundle`。
- 同一响应的 CSP 为 `default-src 'self'; script-src 'self'; style-src 'self'; ...`，不允许上述外部资源，也不允许该内联初始化。正常遵守 CSP 的浏览器无法初始化这个交互文档页。
- `GET /openapi.json` 为 200，业务 API 未受此问题影响。本项依据实际响应头与 HTML 核对；没有在本聊天执行浏览器视觉验证。
- 建议：让 API 文档的资源加载及初始化与 CSP 一致，或者明确移除不可用的交互文档入口并提供可用的接口说明。不要为此放宽整个工作台的脚本策略。
- 复核：浏览器打开 `/api/docs`，确认接口列表可见、展开并调用接口可用，控制台没有这些 CSP 阻止记录。

## 验证命令与结果

工作目录均为 `C:/Users/Admin/Desktop/quant`。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

首次结果：19 passed、6 errors、2 warnings。6 errors 全部是夹具创建前访问系统 `Temp/pytest-of-Admin` 的 PermissionError，另外默认 pytest 缓存目录也有权限警告；属于运行环境路径权限，不是产品功能失败。随后使用独立项目内目录重新执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .runtime\review-pytest-1 -o cache_dir=.runtime\review-pytest-cache
```

结果：**25 passed in 2.55s**，退出码 0。适配器测试 12 项、应用测试 4 项、校验测试 9 项。

```powershell
.\.venv\Scripts\python.exe .runtime\phase1_review_probe.py
```

结果：**8 组检查通过**，退出码 0。这是本次审查新增的临时检查脚本，不属于产品或现有测试套件；每次使用新建的独立数据库目录。首轮证据目录：`.runtime/review-probes-3168bbdd4147414e9bcba98b83a07c5f`。

| 组 | 验证内容 | 真实与替身边界 |
| --- | --- | --- |
| 1 | TXT、SRT、VTT 上传、正文、真实时间戳、无时间戳文本保持 null | 真实 FastAPI 接口、解析器及 SQLite |
| 2 | 空媒体、非法字幕、非 UTF-8 文本被拒绝，上传临时文件清理 | 真实接口及文件系统 |
| 3 | 生成的有效 WAV 上传，媒体接口读回同样字节；ASR 缺失明确失败，重试仍明确失败 | 真实上传/媒体/任务流程；没有执行语音识别 |
| 4 | Bilibili 和抖音分享 URL 保存，未配置 ASR 时明确失败 | 仅 DNS 解析使用固定公网地址替身；没有平台下载 |
| 5 | 重建应用后资料列表及失败任务仍保留 | 真实 SQLite 持久化和应用生命周期 |
| 6 | 正在提取时重复任务、编辑及重试返回 409；完成后能导出，替身 provider 为 test | 真实 API/调度/存储；提取器为受控测试替身 |
| 7 | OpenAI 兼容请求路径/认证/JSON 格式；错误引用拒绝保存；恢复有效响应后重试导出；HTTP 401 明确失败且保留旧有效草案 | 真实 httpx 到本地 HTTP 服务；响应内容为显式测试替身 |
| 8 | Ollama 请求路径/schema/无 Bearer 认证；同样的引用失败、恢复重试、导出及 HTTP 401 处理 | 真实 httpx 到本地 HTTP 服务；响应内容为显式测试替身 |

现有 25 项测试另覆盖：原文逐字引用和时间戳派生、伪造引用/编号/阈值/额外字段拒绝、模糊条件及缺失项提示、字幕时间错误、重复 JSON 字段、转写修订及持久化、旧策略标记并拒绝导出、AI 缺失、任务重启中断、上传大小及类型限制、CSRF/Host/版本冲突、URL 基础约束和内网连接阻止。其中成功提取使用 `tests/test_app.py::FakeExtractor`，不是真实 AI。

```powershell
.\.venv\Scripts\python.exe scripts\check_environment.py
```

结果：退出码 0；Python 3.12.14；faster-whisper 1.2.1、PyAV 19.0.2、CTranslate2 4.8.5、FastAPI 0.162.2 导入正常，yt-dlp 导入正常。`asr_configured=false`、`ai_configured=false`。依赖导入成功不代表模型可用。

R1 最小复现命令：

```powershell
@'
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
with tempfile.TemporaryDirectory(dir='.runtime', prefix='review-docs-') as tmp:
    with TestClient(create_app(Settings(data_dir=Path(tmp)))) as c:
        r = c.get('/api/docs')
        print(r.status_code, r.headers.get('Content-Security-Policy'))
        for line in r.text.splitlines():
            if any(s in line for s in ['<script', '<link', 'SwaggerUIBundle']):
                print(line.strip())
        print('openapi', c.get('/openapi.json').status_code)
'@ | .\.venv\Scripts\python.exe -
```

## 需求对齐与边界

- 已阅读 `PRODUCT.md`、`IMPLEMENTATION.md`、`.env.example`、`app/`、现有 `tests/test_*.py` 和启动/环境脚本。审查时 README 尚未生成；属于实现仍在收尾的文档，不据此判为产品缺陷。
- 没有组合、回测、模拟盘或下单功能扩张。策略保存为待人工核对草案，`executable=false`。
- 规则、标的和周期依赖转写中的逐字证据，时间由真实分段派生；不允许模型自行增加时间戳。
- AI/ASR 未配置有清晰反馈；接口状态不暴露 API key。成功路径测试替身没有混入正常启动脚本。
- 编辑有版本检查且任务期间受保护；编辑后旧草案标记过期并禁止导出。服务恢复会将未完成任务标记中断，允许重新提交。
- 未实测：真实平台获取、真实模型 ASR、真实模型语义提取效果、媒体任务长时间运行/超时、GPU、Linux、前端交互和移动视口。本轮范围允许前述模型缺失；其他运行环境结论不外推。
- 通过证据反映审查当时文件，若实现后续修改后端，需针对改动复核。核心文件 SHA256：`app/main.py` = `159EE3DEA52F82709BDD11DB3E8538A627855ECB38ED5CF1AFD757A18C438CA9`。
