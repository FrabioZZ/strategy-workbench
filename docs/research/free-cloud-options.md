# 小体量云部署选型记录

核查日期：2026-11-09（Asia/Shanghai）。用户选择：**腾讯云一个月免费试用**。尚未创建实例、产生费用或完成云端测试。价格、试用资格、地区和库存以用户实际控制台订单为准。

后续范围更新：用户在注册/领取期间改为先做本地MVP，云计算迁移与持续运行不属于一期。本记录仅供未来选型参考，当前不继续推进试用领取或云部署；用户账号实际创建情况尚未核验。

## 已核查的选项

| 平台 | 当前官方说明 | 对本项目的判断 |
| --- | --- | --- |
| 腾讯云轻量应用服务器 | 免费体验馆列有个人2核2GB、3Mbps、40GB系统盘、200GB流量包，1个月试用；另有其他档位，领取资格按账号和活动确定 | 本轮选择。先用Ubuntu进行串行视频获取验证，再根据结果安排应用部署。限时试用，不是长期免费 |
| Oracle Cloud Always Free | 当前文档的ARM额度为每月1,500 OCPU小时及9,000 GB小时，相当于2 OCPU/12GB；有200GB块存储额度。可能无容量或回收闲置实例；注册需要银行卡验证 | 长期免费额度的备选，当前未选择。不能照搬旧文章的4核/24GB。ARM依赖与转写性能需实测 |
| Render Free | 空闲15分钟休眠；重启/休眠/部署会丢失本地文件；免费实例不能挂持久磁盘；免费Postgres 30天后到期 | 可作临时展示，当前SQLite与缓存文件原型不宜直接搬上去，更不适合作为持续模拟盘运行方案 |
| Hugging Face Spaces | 当前文档表示新建Gradio/Docker Spaces需付费计划；静态Spaces仍免费，符合条件的免费个人账号另有ZeroGPU例外 | 不采用旧教程所称“任意免费Docker Space直接部署FastAPI”的假设 |

来源：[腾讯云免费体验馆](https://cloud.tencent.com/act/pro/free)、[Oracle Always Free资源](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)、[Oracle注册与免费条件](https://www.oracle.com/cloud/free/faq/)、[Render免费实例限制](https://render.com/docs/free)、[Hugging Face Spaces概览](https://huggingface.co/docs/hub/spaces-overview)。

## 当前执行边界

- 用户本人完成腾讯云注册、实名认证与试用领取；确认0元订单、试用结束时间和自动续费状态。不索取聊天中的密码、银行卡信息或密钥。
- Phase 1C先准备独立CLI验证包，运行真实小样本并记录环境、耗时、结果及限制，不启动面向公众的资料API。云服务器上成功取得媒体才记作云端获取成功；本机成功不能代替。
- 初始验证不加载ASR/AI模型，不因低配机器直接承诺未来转写速度、并发或模拟盘稳定性。后续根据真实资源测量定规格。
- 免费计算资源不等于免费模型API、无限存储或无限流量；试用结束后需作续费、迁移或释放决定。
- 当前本地应用尚无正式多用户隔离与公网运行条件。手机访问部署须另补身份认证、资料所有权、任务持久化及HTTPS等，按Phase 1C迁移差距记录推进。

阶段索引：[Phase 1C](../phase-1c-index.md)。
