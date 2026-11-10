# python-spider 视频下载功能评估

核对日期：2026-11-09。用户提供仓库：https://github.com/Jack-Cherish/python-spider 。本评估读取仓库元数据、完整目录树、README 和相关文件；没有执行这些文件，也没有访问其中的签名或第三方解析服务。

## 结论

“用户提交社交媒体链接，软件后台获取媒体”的功能可以集成到现有软件。这个仓库适合用作历史实现参考，但不适合直接复制为本产品的下载依赖。Phase 1B 将继续以已有的 yt-dlp 适配器独立实现，补足分享文案解析、下载与转写分离及失败反馈。

这是工程选型判断，不是断言仓库的每个接口都已经失效；本次没有运行旧脚本验证接口可用性。

## 核对依据

| 来源 | 实际看到的内容 | 对本项目的影响 |
| --- | --- | --- |
| [根 README](https://github.com/Jack-Cherish/python-spider/blob/master/README.md) | 明确限制学习参考用途并禁止商业用途 | 不能把公开仓库直接视为允许本产品复制使用的宽松许可证；本轮不复制代码。如将来确需采用，应先确认相应授权 |
| [仓库元数据](https://api.github.com/repos/Jack-Cherish/python-spider) | GitHub `license` 字段为 null，`pushed_at` 为 2024-08-19；递归目录树未见根许可证文件 | 没有找到可据以直接采用的 MIT/Apache 等宽松许可；最后推送时间不代表各平台脚本最近被验证 |
| [douyin/douyin.py](https://github.com/Jack-Cherish/python-spider/blob/master/douyin/douyin.py) | 主流程按用户 UID 批量读取作品/收藏，调用旧 `web/api/v2`，依赖硬编码 HTTP 签名服务；存在无上限重试 | 与单个分享链接导入需求不同，不能直接作为稳定后台任务；不会调用其签名服务 |
| [douyin/README.md](https://github.com/Jack-Cherish/python-spider/blob/master/douyin/README.md) | 说明签名服务依赖，并提及服务关闭后的替代方向 | 仓库本身不是自包含的当前平台下载服务 |
| [bilibili/bilibili.py](https://github.com/Jack-Cherish/python-spider/blob/master/bilibili/bilibili.py) | 文件标注 2018 年；主要按关键词分页批量下载，解析固定页面片段和 durl，部分请求关闭 TLS 校验，合并调用拼接 shell 命令 | 与当前单链接流程、输入隔离及可迁移后台任务不匹配；本轮不引入这些实现 |
| [2020/bilibili/download.py](https://github.com/Jack-Cherish/python-spider/blob/master/2020/bilibili/download.py) | 文件标注 2020 年；第三方解析地址为 `xxx`，通过 Windows 迅雷 COM 添加任务 | 代码不完整，且依赖桌面软件，不适合作为未来服务器下载模块 |

## 本项目实际缺口

评估时的现有实现已有链接输入、域名校验和 yt-dlp 工作进程。但 `app/jobs.py` 在下载前先检查 ASR 模型，导致用户未准备语音模型时连获取媒体都不能开始；前端 URL 输入也不接受平台复制的整段分享文案。

Phase 1B 的重点应为：抽取唯一支持的视频链接 → 校验与解析 → 后台有界下载并缓存 → 如实显示媒体状态 → 模型准备好后再转写。下载是否成功不应由 AI 或 ASR 是否配置决定。

## 验证边界

链接解析和任务流程可通过自动化测试验证；平台是否允许当前请求、具体链接是否需要登录/验证或已失效，必须用真实链接另行测试。不能用测试替身或仓库 README 中的功能描述代替真实下载证据。用户自己的浏览器凭据不自动读取；视频画面识别、整账号采集与交易功能不在本阶段范围。

后续开发与验收索引：`../phase-1b-index.md`，可见协调聊天 `Phase 1B - 社交视频链接导入协调`（`01a1bf39-44f1-7af1-8e61-ded13e3981c7`）。
