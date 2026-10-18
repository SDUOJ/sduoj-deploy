# 普通文档 Agent 前端 dev 验收

2026-10-19 检查点。第一阶段范围仍见 [11](11-dev实施进度.md)，后端与真实模型证据见 [12](12-Agent后端dev验收.md)、本人端点见 [13](13-本人端点dev验收.md)。本轮仅修改 web2；AutoLab 保持 b45a667，运行时代码保持 0bf775c，生产与组件安装配置均未改。

## 入口与行为

web2 检查点 `c703cfb` 提供 dev-only `/v2/workspace/document-translations`，复用现有登录、Redux 和 `request.ts`。页面不套旧的 `AIRouteBoundary`，渲染不取决于站点 provider 或平台积分；实际 API 仍按原会话、账户状态、本人、admin 角色及课程/题单权限决定是否允许读取与写入。

- 来源列表调用既有 `resources/list(kind=document)`，默认只列本人当前可读文档，分页 20。列表投影仅保留 ID/标题/版本；不表示附件、native 引用或无正文资料可被普通文本适配器接受。详情再次校验普通文本、版本和 UTF-8 边界。本页不新增文档上传或编辑流程。
- 选择中文/英文及本人显式端点或本人默认。当前作用域的组件/action 开关决定创建控制的显示，available/can_start、有效密钥、明确价格和 active 端点决定是否可点击；服务端才是最终准入权威。无默认、未知价格或无端点不会改用站点 provider。
- 创建前重新 GET 来源；版本或正文变化时只更新预览，提示检查后再点，不自动提交未展示内容。读取等待期间组件撤回或缓存过期也不能创建。typed admission 返回原 TaskJob ID；每次新任务由服务端重新冻结来源、策略、端点与费率。
- 原 `jobs/{id}` 自主轮询在读取完成后再计时，终态停止；手动刷新通过请求 ID 隔离逆序响应，查询失败可刷新恢复。取消使用原入口，不受组件开关隐藏；取消与完成竞态后重新读真实状态。失败或取消后不调用 generic retry，而是显式新建任务。
- 成功任务按 task/attempt/source/hash/version 绑定候选；原文、独立已保存译文和候选都用文本展示。采纳需人工勾选与说明，发送候选版本/hash 和唯一 operation key；服务端重核来源、当前权限、策略、过期、账务与 CAS。采纳成功后重读来源与候选，不以旧 receipt 替代当前状态。
- 未确认的 create/adopt 保留原操作正文与 key，显式重试精确重发。放弃重试会提醒可能已有任务，刷新核对；不自动创建替代任务。任务列表为 `agent.run` 增加来源/任务深链，可重新进入候选页。

## 缓存与开关

新增作用域 hook 已实际用于本页，既有 Redux 仍是唯一共享缓存。30 秒到期隐藏旧控制并刷新，错误关闭控制；同 store/scope/epoch 的多个消费者共享在途请求，发起者卸载不丢弃仍有效的共享响应。停止组件不删除历史或端点修复入口。

文档私有缓存与能力缓存按 userId、username、去重排序后的 roles/groups 失效。原 ACL 依赖用户组与用户名，不能仅跟踪角色。撤回后恢复的 ABA、请求逆序、不同作用域与卸载均有反例。

这仅证明新页面消费了能力 hook。其他历史页面的菜单、路由、按钮，以及旧后端模型链尚未全部接入统一治理，不能据此启用组件；`INSTALLED_COMPONENTS` 仍为空。

## 聚焦提交与独立审计

| 提交 | 目的与审计结果 |
| --- | --- |
| 5cee7cd → 0ef4b69 | typed 客户端与私有 Redux；独立审计发现组/用户名未进入缓存指纹，已修复并保留初始反例 |
| d6571cc → 3159614 | 能力自动刷新；共享 scope 请求被卸载消费者丢弃的问题已复现并修复 |
| 2371d24 → 51e0606 | 来源摘要分页；缺 type import 导致精确提交 tsc 失败，已单行修复，保留失败日志 |
| 9d26656 → 2bcc4af | 页面与候选确认；独立审计复现旧来源版本仍被发送，改为刷新后重新确认 |
| 4d5b3ce | 确认弹窗取消文案准确本地化，发送期间禁止关闭 |
| c703cfb | 将候选有效性与确认期间的控件锁分开，避免打开合法弹窗时误报失效；确认按钮仍跟随当前能力失效禁用 |

本轮新增提交逐笔审计，不扩张为全部历史提交已深审。

## 验证证据与边界

- `4d5b3ce` 上 15 suites / 219 项通过（33.588 秒），覆盖页面、typed API、三个私有 reducer、共享能力 hook、旧端点页面、任务入口及 dev/production 路由门禁。TypeScript 和目标 ESLint 通过。既有 developmentRoutes 测试有一次 rc-menu 的 act 警告，测试通过；没有为消除警告改产品实现。
- 后续仅修正确认锁与失效提示的 `c703cfb`，针对当前页面重跑 14 项通过（7.492 秒），TypeScript/目标 ESLint 通过。未将旧 SHA 的 219 项或浏览器中较早的创建/取消步骤冒充本次重跑。
- 独立客户端审计补真实 ASGI + 隔离 SQLite 的 source/task/candidate/adoption/replay DTO，列表审计验证 23 条本人文档的 20/3/0 分页及失权/软删/他人过滤。这证明 HTTP 合同，不证明 MySQL 锁、真实网关身份或真实模型。
- 组件测试和 Chromium 使用合成 API，未访问真实模型、生产或现有用户会话。之前 [12](12-Agent后端dev验收.md) 的真实模型任务仍是独立证据，不能与 mock 浏览器拼接成完整站点验收。
- 固定 `c703cfb` 的全新 Chromium 会话完成创建 → 取消 → 新建另一任务 → 候选 → 人工确认 → 重读已保存译文，录得 2 次 create（不同操作 key）、1 次 cancel、1 次 adopt。375px 下页面宽 367px、弹窗 359px（显示期间 document 宽 375px）；1440px 下页面宽 1432px。原文保留，未插入候选中的 HTML，pageerror 为 0。首轮截图/尺寸受 AntD 开合动画影响，保留后改为等待动画结束再采集；稳定证据为 `stable-flow.json` 与 `stable-*.png`。
- 失败记录保留：初始组权限反例、共享请求反例、picker tsc 失败、旧来源版本反例，以及初轮页面测试引用已被重新挂载按钮的错误。未把后续通过倒填到初始 SHA。

本机工作目录 `platform-v2-implementation-20261018` 保存 `audit-document-agent-{client,picker,page}.md/json`、`audit-capability-hook.md/json`、`document-agent-combined-final-tests.json` 与 `output/playwright/document-agent/`；这些证据未加入源码，也不包含真实端点密钥。

## 后续

继续统一旧 AI admission/claim/模型/工具/采用链的组件 gate，并将能力发现接到其他页面。之后以隔离环境验证真实网关/身份 RPC、Redis 与 Linux SDK 安装、完整业务浏览器链，再逐批安装 14 个组件。48 项任务与原发布门禁保持不变；本页完成不等于可以启用或发布 platform v2。
