# Phase 1 — R1 API 文档修复复验

日期：2026-11-09（Asia/Shanghai）  
目录：`C:/Users/Admin/Desktop/quant`；非 Git 仓库，无分支或独立 worktree。  
范围：仅复核 `docs/phase-1-review.md` 的 R1，并补充文档说明。原验收报告保留历史结论，不作修改。

## 结论

**R1 已通过独立复验，可关闭。** 本地只读文档页在真实 Chrome 浏览器中正常显示当前 OpenAPI 的全部方法/路径，支持展开结构和打开完整 JSON；未发生 CSP 违规或脚本异常。全站 CSP 保持严格策略，无外部 CDN 依赖。

这仅是 R1 的验收结论，不替代整个一期的前端主流程、真实 ASR 或真实 AI 验收。

## 修复归属与边界

收到协调更新时，实现聊天已完成主体修复，因此保留其方案，没有重复重写：

| 文件 | 现有修复 / 本聊天变更 |
| --- | --- |
| `app/main.py` | 实现聊天已设置 `docs_url=None`、`redoc_url=None`，`GET /api/docs` 返回本地 `frontend/api.html`，并设置 `include_in_schema=False`。本聊天未修改后端代码。 |
| `frontend/api.html` | 实现聊天已创建中文页面，仅加载 `/static/style.css` 和 `/static/api.js`。本聊天补充“只读、不提供在线试调用”的说明。 |
| `frontend/api.js` | 实现聊天已通过同源 `fetch('/openapi.json')` 枚举真实接口，并用 DOM `textContent` 展示结构。本聊天未修改脚本。 |
| `README.md` | 本聊天明确本地脚本、只读用途、可展开结构及无 CDN 依赖。 |
| `.runtime/r1_docs_*`、`output/playwright/r1-*` | 本聊天的隔离复验脚本、结果及浏览器证据；不进入生产启动流程。 |

本页需要浏览器启用同源 JavaScript；“离线可用”指本地服务运行时无需外部网络，不代表停掉服务后可用。页面只展示定义，没有 Swagger 的试调用功能。依据协调者最新要求接受本地 JS 方案，不再要求零脚本或为验收添加试调用功能。

没有放宽 CSP，没有添加依赖、模型调用或其他产品功能。

## 验证结果

### 1. 现有测试套件

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .runtime\fix-r1-pytest-1 -p no:cacheprovider
```

实际输出：`30 passed in 1.67s`，退出码 0。委派时提到的 25 项已由实现聊天扩展为 30 项，本次执行的是当时完整的现有套件。使用独立项目内临时目录并关闭 pytest 缓存，未遇到临时目录权限错误；没有改动现有测试文件。

### 2. HTTP 与资源核对

```powershell
.\.venv\Scripts\python.exe .runtime\r1_docs_probe.py
node --check frontend/api.js
```

均退出码 0。检查内容：

- `/api/docs`、`/static/api.js`、`/static/style.css`、`/openapi.json`、`/api/status`、`/api/documents` 和 `/` 均为 200。
- 文档响应为 HTML，页面包含只读说明及 `/openapi.json` 链接。
- 唯一脚本是同源 `/static/api.js`，无内联脚本、内联事件处理器或外部脚本/样式资源。
- 文档及上述路由的 CSP 均与原严格策略逐字一致：

```text
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'
```

证据：[HTTP 检查结果](../.runtime/r1-docs-http-result.json)。独立数据目录为 `.runtime/fix-r1-http-379f4bf3f69e42f39707fb7699b1568f`，未使用业务 `data/`。

### 3. 真实浏览器复核

使用本机已有的 Node.js、Codex bundled Playwright 和 Chrome，无安装或下载步骤。沿用项目现有脚本式 Playwright 方式执行独立检查：

```powershell
$env:NODE_PATH = 'C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1104-2876-0_26.1104.2876.0_x64__3k8sg7r9htsxt\dependencies\node\node_modules'
node .runtime\r1_docs_browser.cjs
```

结果 `PASS`，退出码 0。该脚本启动只绑定 `127.0.0.1` 的隔离服务，端口由操作系统分配；结束时关闭浏览器及其自启服务。数据目录为 `.runtime/fix-r1-browser-1794204571580`。

| 检查 | 结果 |
| --- | --- |
| `/api/docs` 响应 | 200 |
| 渲染的方法/路径与当前 OpenAPI 比对 | 全部 13 项一致，其中 12 项为 `/api/` 业务接口，另 1 项为 `GET /` |
| `POST /api/documents/text` 的请求/响应结构 | 可展开、内容可见，包含 `TextImport` 引用 |
| 数据模型定义 | 可展开、内容可见，包含 `TextImport` 定义 |
| 完整 OpenAPI JSON 链接 | 可打开并包含真实接口路径 |
| `/api/status` | 200 |
| 外部网络请求 | 0；浏览器路由检查会阻止并记录任何外部请求，实际未触发 |
| `securitypolicyviolation` 事件 | 0 |
| 控制台 CSP 错误 | 0 |
| 页面 JavaScript 异常 | 0 |

实际页面请求仅涉及 `/api/docs`、`/static/style.css`、`/static/api.js` 和 `/openapi.json`。没有通过文档页发送业务写入、提取或下载请求。页面收到的初始 HTML 是静态外壳，真实接口列表由本地脚本读取 OpenAPI 后显示；浏览器验证覆盖了这一过程，不能仅凭 HTTP 200 断言页面可用。

证据：

- [浏览器检查结果](../output/playwright/r1-api-docs-result.json)
- [页面语义快照](../output/playwright/r1-api-docs-snapshot.txt)
- [展开接口与数据模型的完整页面截图](../output/playwright/r1-api-docs.png)

## 复验文件指纹

以下 SHA256 用于协调者判断后续改动是否需要复核：

| 文件 | SHA256 |
| --- | --- |
| `app/main.py` | `C86540E54DC13AEEA7749F58E16E2DDAE7D770B91EB8C8E7F7D8665F4961FF19` |
| `frontend/api.html` | `5F2743B1F12B4201C674D729B3DE2C24770C7E6985E92BF204CE49C9463400A5` |
| `frontend/api.js` | `34FCFBA5F2339D745856C4513B802BFE92C2B347D44A2B3CF56BB5A5003E94D6` |
| `README.md` | `E46749A5282303EA13E1B1190603F639056D558F6747278843E5E0938EE270B0` |
| 原报告 `docs/phase-1-review.md` | `696893B36F10D304C46EA219BF4F8DFB401189EFC85271A4DC680CB85D378E56` |

本聊天采用 systematic-debugging 定位并核对既有修复，使用 Playwright 及 verification-before-completion 完成验证。未进行对抗审计，未新增其他聊天或后台子代理。
