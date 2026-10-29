# 端点运营与停用 dev 验收

2026-10-19，承接 [27](27-端点探测前端与真实供应商dev验收.md)。本轮实现第一阶段已批准的“平台 superadmin 仅查看脱敏端点元数据和停用”，不增加角色、schema、委托或模型出口。AutoLab 检查点 `99b073a`，web2 功能检查点 `aa66d9b`；仅本地 dev 提交，不 push、不改生产、Java、镜像或发布链。

## 运营合同

原 `/auto-task/ai` 前缀下：

| 接口 | 行为 |
| --- | --- |
| `GET /admin/ports?offset=0&owner_id=…&status=…` | 原 superadmin；20 条分页、属主 ID/状态精确过滤、时间/ID 稳定倒序，不显示 deleted。只 SELECT，不创建账号或锁行。 |
| `POST /admin/ports/{id}/disable` | 原 superadmin；必须 version、operation_key、非空 reason，CAS 停用并清默认，持久化原 AiResource/AiRevision 审计/幂等回执。 |

列表只返回 id、owner_id、名称、提供商 hostname、模型、Responses/OpenHands/release、状态/版本、has_key、并发和预算、UTC 创建/更新时间。不回传完整 URL 或路径、key/cipher、指纹/secret key ID、能力原记录、任务 payload 或用户请求用量明细。hostname 允许原合法 IPv6/IDNA，客户端只本地验证语法，不访问 DNS/提供商。本人端点的列表、用量和启用等 API 保持 owner-only，运营权限不提供代用户调用模型的能力。

停用复用 runtime → 稳定属主账户 → 回执/端点锁和原计费权威。已发送的请求继续结算，账本、任务、历史不删除；后续 `current_port` 检查拒绝旧冻结配置，不换备用端点。排队探测按原 claim 变 blocked，原取消仍可清理。这是端点停用，不是永久封禁：属主可按原 CAS 明确重新启用，但默认标记不自动恢复。旧操作重放返回历史 receipt，不重做停用或覆盖当前列表。

## 前端使用

dev 账户管理页 `/v2/account/assistant` 的“端点运营”只对已登录原 superadmin 显示；AI 账号暂停时仍保留修复入口，后端仍独立验证运营角色。普通 admin/USER 不获取全站信息。

列表和过滤状态进入原 Redux，绑定 subject/角色代次/请求 ID/过滤条件。新读取清旧列表，失败只显示固定提示；跨账号、角色 ABA、退出和旧响应不恢复全站数据。停用弹窗展示属主/版本和影响，必须填写原因；快速重复点击不产生第二写入。未知写冻结原正文/原因/版本/key，只能显式重试同操作。成功或“关闭并刷新”都重新读取当前列表，不能将可能已过时的回执显示成现态。

## 逐提交审计与失败记录

- AutoLab `33989a2` 元数据/停用：独立 exact archive 59 项通过，另 6 项语义边界通过；范围是 SQLite/源码锁序，不能外推真实并发。
- `898917b` 新增真实 MySQL 多进程/旧 RR 测试，根组合 61 通过、1 失败，4.05 秒。诊断明确管理员 DB1213；独立确定性反例也失败。原因是管理员先对缺失回执加 gap lock，再等属主账户；属主持账户插回执时等该 gap，形成互等。测试提交正确暴露初稿缺陷，不能当作通过的交付树。
- `53ae54e` 将稳定属主锁移到回执 gap 之前。根 62 通过、4.01 秒、退出 0；独立 exact archive 62 通过、4.19 秒，原确定性死锁反例修复后通过。同操作跨进程仅一笔回执，属主/管理员同版本竞争仅一方成功，旧 RR/identity-map 不能覆盖新版本。
- `ef731e4` 原 Gateway 验收：根 1 项通过、1.70 秒；独立 1 项通过、1.79 秒，均退出 0。原 Java 临时 USER、登录/角色/fresh RPC、Gateway、自有 MySQL/Redis 和原 worker：USER 运营接口 403，管理员脱敏读取/停用/重放，旧排队 probe blocked 且 0 AiRun，管理员仍不能进入他人 owner API。属主显式重启后，旧运营 receipt 不改 active 现态。没有模型请求。
- web2 `52ec4ef` typed client/Redux 初稿原 29 项通过，但独立两项合法 IPv6/IDNA 反例失败，整页会因合法 host 被拒绝而不能展示。`a4349f9` 支持原合法 hostname，同时继续拒绝 URL/路径/凭据/port/转义；独立 41 项通过、tsc/ESLint 通过，旧 needs_fix 保留。
- `01c4fc6` UI 根相关 15 项通过，独立新增未知写关闭反例失败：“关闭并刷新”未真正刷新。`aa66d9b` 关闭先清确认、重读原过滤列表；同时将表单 reset 移到挂载后，修复实际浏览器的 useForm 未连接 warning。根新 UI 12 项通过、14.076 秒；独立 17 项通过、tsc/ESLint 通过，原反例与 needs_fix 保留。
- `99b073a` 显式浏览器 fixture 离线独立 3 项 guard 通过，未 opt-in 正确跳过；没有把离线 guard 当成真实浏览器执行。根最初的组件测试因误用取消按钮文案和搜索输入事件而失败，日志保留，修正测试选择器后才记录通过。

## 真实浏览器与全量

真实 Chromium → 原 webpack proxy → Gateway/Java 登录 → AutoLab → 随机自有 MySQL/Redis，未替换页面 API/身份/模型。首次 `01c4fc6` 完成读列表、原因确认、停用和版本 2，1 项通过、158.08 秒、退出 0，但观察到表单 warning；不能称作无 console error。

修订 `aa66d9b` 再跑同 fixture：关闭确认时观察到实际元数据 GET 200，重开并填写原因，停用后重读 disabled/version2。最终 **1 项通过、205.86 秒、父进程退出 0**，0 TaskJob、0 AiRun、0 模型请求；最终登录会话打开/关闭/重开/提交无新 console error，有 5 条既有开发 warning。375px 下 panel clientWidth/scrollWidth 均 333，卡片均 331，无横向溢出。两个临时 USER 由原 Java fixture 清理，browser-auth 已删除、浏览器及 5005/3016 临时服务已退出，原 dev 容器未调整。

最终 clean AutoLab `99b073a` 全量 **1070 通过、24 跳过、96.64 秒、父进程退出 0**；真实 SDK 解释器和随机自有 MySQL 启用，Gateway/live-provider 专用 opt-in 默认跳过。固定库/容器等未运行项仍不计覆盖。最终 clean web2 `d2a098c` 全量 **178 suites / 1339 项全部通过，322.257 秒、父进程退出 0**，目标 TypeScript/ESLint 通过。较早 `01c4fc6` 全量因已确认关闭缺陷而中止（退出 143），不记通过。

`aa66d9b` 全量保留 **1337 通过、2 失败、352.208 秒、退出 1**。其一是既有英文题目导入 Modal 在默认 1000ms 时仍处于 opacity=0 的动画 prepare 阶段，独立整套 6 通过、1 失败；单点等待 5000ms 后原可见性/英文断言全部保留并通过（`a67bfa7` 独立 7 项通过、18.481 秒）。其二是 root logout 兼容测试未识别新增运营 reducer 的单调 epoch，初次 `d22856b` 虽通过，但独立审计发现身份切换提前清除了原 Agent 缓存，弱化原覆盖。`d2a098c` 在两份缓存预热前建立身份，并在 logout 前断言两份状态都 ready，再核对内容清空和 epoch 递增；独立两 suites 40 项通过。独立 mutation 故意让原 Agent logout 不清 entries，新增时序能稳定捕获失败，证明恢复了原清除覆盖；原退化反例保留。较早 `d22856b` 全量据此停止（退出 143），不记通过。这两个后续提交只改测试，产品行为保持 `aa66d9b` 的真实浏览器检查点。

## 记录与下一步

仓库外 `platform-v2-implementation-20261018` 保存明确命名的 `port-admin-*` 回归/截图、`gateway-port-admin*.log`、`audit-port-admin-*.md/json` 和两个 `port-admin-browser*` 控制目录的公开 result。目录另有凭据，禁止 JSON glob 读取；读取审计证据必须指定文件名。

31 份明确命名的文本日志/审计报告，以及另 13 份明确文档/报告/快照，已扫描测试 API key、dev 密码、RPC token、本地 MySQL/Redis 密码，均 0 命中；不包括工具输出、图片或扫描后追加的文本。最终两份冻结全量日志及本验收文档结束后另 3 文件复查，0 命中。

运营页面不代表更广的用量/队列/错误跨用户聚合已完成；本次仅已批准的元数据和停用。受控 models 发现、实际端点用户矩阵、其余 12 个业务组件、原生 MySQL 锁矩阵、最终 Linux amd64/制品仍待推进，原 48 项任务状态不因本轮通过整体改 done。
