# models 任务与前端 dev 验收

2026-10-19，承接 [29](29-models受控出口dev验收.md)。本轮将显式元数据出口接入原本人端点、TaskJob、独立 worker 和前端；不增加 Agent 组件安装或角色，不改 Java、schema、镜像或发布链，不 push、不改生产。最终 AutoLab `8df0777`，web2 `79a6ec9`。

## 接口与执行合同

原 `/auto-task/ai` 前缀新增四个本人端点接口：

| 接口 | 行为 |
| --- | --- |
| `GET /ports/{id}/models` | 本地请求范围：当前版本、最多 1 次目录 GET、0 推理、30 秒、262144 响应字节；不解密、不访问提供商、不创建账号/任务。 |
| `POST /ports/{id}/models` | 必须 version、confirmed=true、operation_key；创建原 `port.models` 任务，固定 `models-probe-v1`，max_attempts=1。 |
| `GET /ports/{id}/models/latest` | 最近一次本人诊断或 null；原冻结版本和安全状态，停用/暂停后仍可读历史，已删除端点不再读取。 |
| `GET /ports/{id}/models/{taskId}` | 绑定同一 owner/payer/port/type/harness，只返回生命周期、UTC 时间和闭合观察。 |

原登录和可信 Gateway 边界保留，superadmin 不能代读别人的本人接口。实际执行每个边界走原 fresh Java 身份，不使用 debug 身份绕过。准入继续原 active 账号、积分/未结用量门禁；元数据不要求模型费率，但不能因此绕过账号停用或建立任意匿名出口。

冻结 payload 只含端点 ID、版本和服务器配置/密文身份的不可逆绑定摘要，不包含 key、cipher、URL 或模型正文。runtime → task → account → port 的锁序和当前读取拒绝配置漂移；与 `port.test` 双向共享每用户 3 次/分钟、1 个未终结诊断限制。领取时，元数据与同端点的其他任务双向互斥，避免没有推理预留的 GET 越过端点并发限制。

worker 在外部发送前提交原 AiResource 的 sending 回执。同 lease 再次进入也不能重复发送；崩溃、取消、期限到期或不确定结果不自动重放，通用 retry 仍拒绝该任务。成功后保存 complete 闭合回执；canonical complete 忽略调用者 result/apply，重验本人/配置/回执，只从持久回执取结果，并拒绝混入 AiRun。取消沿原任务权限和接口，迟到完成不能覆盖取消。

这次 GET 没有推理 token，不创建虚假的零 token AiRun 或积分结算，不改变原三次 Responses 的报价/预留/结算或 `AiPort.capabilities`。目录观察独立保存；404 不代表 Responses 不支持，目录成功也不授权模型或工具。提供商原响应、模型 ID/名称列表、密钥和错误正文不出现在诊断结果中。

## 前端

dev `/v2/account/assistant/ports` 增加“模型目录诊断”。打开/刷新只读历史；用户先查看请求范围、勾选确认，再明确创建一次任务。未定模型价格也可运行元数据诊断；停用端点保留历史但不能新建。

服务器状态进入原 ModelPorts Redux，绑定 subject/角色 epoch、当前列表请求/版本及诊断请求 ID。关闭、账号/角色 ABA、退出、列表刷新和旧响应都不能恢复旧私有数据。运行中按原任务 ID 轮询，终态/卸载停止；不因轮询创建新任务。未知 start/cancel 写冻结原正文、版本和操作 key，只有显式重试；已知创建回执后的读取失败只重读原任务。历史版本可读并显示警告，不能冒充当前端点验证。中英文均显示本次观察、模型数量、延迟和本地分钟提交时间。

## 逐提交审计与失败记录

- AutoLab `0ef716e` 产品/合同：根定向 98 项通过，6.56 秒；独立 exact archive 原五套 125 项通过，6.69 秒，另 13 项安全反例通过，0.86 秒，accepted。覆盖 durable 输入损坏、sending 后进程崩溃及同 lease/过期不重发、AiRun 混入拒绝、持久回执额外 provider 字段拒绝、未知价格、负积分/未结用量和通用提交拒绝。均未冒充真实身份或数据库锁证明。
- `071b670` InnoDB 进程测试：根含原 unit/probe 的 52 项通过，4.47 秒；独立原三项 SQL 通过，2.30 秒。但旧 RR 测试未保留 ORM 对象强引用，独立缓存前置探针失败，0.64 秒，证明未实际覆盖 identity map；needs_fix 保留。
- `ca0e9c9` 单独补强强引用和缓存前置断言，保留原 409/零任务断言。根 52 项通过，4.56 秒；独立 exact 的三项真实 SQL 加完全相同的原失败缓存探针共 4 项通过，2.69 秒，accepted。同确认跨进程仅一个 TaskJob，同 lease 竞争仅一次合成发送；身份/提供商仍为替身。
- `9c1e086` 原 Gateway 验收：根 1 项通过，1.83 秒；独立 exact 1 项通过，1.99 秒，均退出 0。原 Java 创建临时 USER、登录/fresh 身份、Gateway、自有 SQL/Redis：确认/取消前不发送、重复确认同任务、一次合成目录、跨属主 404、停用后历史可读、0 AiRun；临时账号和库清理。提供商明确为替身。
- web2 `17858ac` client/Redux：根四套 73 项通过，1.861 秒；独立五套含 7 项新增迟到/绑定反例共 80 项通过，4.313 秒，accepted；TypeScript/目标 ESLint 通过。
- `79a6ec9` 页面：根新 7 项与原探测 16 项共 23 通过，24.81 秒；独立原 23 项通过，27.682 秒，另 8 项取消/轮询/未知写/列表/权限交错反例通过，9.439 秒，accepted；TypeScript/ESLint 通过。
- `8df0777` 显式浏览器 fixture/发送观察器：根离线 20 通过、默认 1 跳过，0.34 秒；独立同检查 20/1，0.59 秒，另 12 项调用前 guard/私有 stdin/旧默认 worker 兼容/失败仍占唯一调用额度等通过，0.36 秒，accepted。离线审计没有调用真实提供商或 Gateway。

根最初 Python 新测试遗漏 database fixture import，23 项 setup error；补齐后才有通过结果。页面初稿测试两项失败分别是第二次重新查询 loading 按钮名、AntD 两字中文按钮自动插空格；改为同一按钮引用双击及可见文案正则后通过。另移除测试不合法的 ByRole exact 类型选项。翻译写入脚本曾在解析时退出，未产生文件修改或网络调用；随后以明确补丁加入双语。原失败日志保留，没有当作产品或提供商失败，也没有削弱业务断言。

## 真实浏览器与最终回归

Chromium → 原 webpack proxy → Gateway/Java 登录 → AutoLab → 随机自有 MySQL/Redis → 原独立进程 worker → 原受控 HTTPS GET。没有替换 API、身份、transport 或组件安装。浏览器先确认一项 queued 诊断并取消，worker 尚未启动，0 外部发送；再明确确认新任务，启动受限观察器包裹的原 worker。

最终 **1 项通过、355.55 秒、父进程退出 0**。一项 cancelled/attempt0、一项 success/attempt1、一个 complete 回执；观察器确认 **1 次 metadata GET、1 次返回、11 次 fresh 身份读取、0 推理、无 SDK**。真实目录观察 supported、21 个模型，页面延迟 378ms。0 AiRun/AiLedger，没有伪造零用量。此浏览器使用既有专用 dev 业务账号；普通 USER 权限链是上面的独立原 Gateway 验收，不拼接为同一浏览器身份。

关闭后重开只读取同一历史，未再创建或发送。桌面及 375px 截图已检查；375 下 documentWidth=375，dialog client/scroll 均 359，body 均 311，无横向溢出。认证页面全过程 0 新 console error、5 条既有开发 warning；恢复 cookie 前旧页面出现的 1 条错误记录保留，不归入认证页面。worker 正常退出 0，Redis 订阅恢复；browser-auth 删除、CLI 浏览器关闭、owned webpack 正常退出 0，5005/3016 已实际 bind 验证释放，原 dev 容器未重配。

最终 clean AutoLab `8df0777`：**1141 通过、25 跳过、849 条 warning，103.59 秒，父进程退出 0**。真实 SDK 解释器和自有随机 MySQL 已启用；容器、固定库、live/Gateway 等专用 opt-in 仍单列跳过，不能把它们算作全量通过。最终 clean web2 `79a6ec9`：**181 suites / 1383 项全部通过，357.742 秒，父进程退出 0**。本页真实浏览器是单独启用的上述验收。

## 证据与后续

仓库外 WORK 保存 `port-models-tasks-*`、`port-models-client*`、`port-models-ui-*`、`port-models-delivery-full-sdk-mysql.log`、`port-models-web-full.log`、`gateway-port-models.log`、`gateway-models-browser.log`、`audit-port-models-{tasks,mysql,mysql-cache-fix,gateway,client,ui,browser-fixture}.md/json`、`models-browser-20261019/result.json` 和 `models-{desktop,mobile}-20261019.png`。目录另有私有配置，禁止 JSON glob；必须按明确证据文件名读取。

元数据诊断的 dev 用户流程已经接通，但不是模型列表选择器、任意提供商支持矩阵或整个平台发布验收。更广的网络/端点用户矩阵、其余 12 业务组件、原生 MySQL 锁矩阵、Linux amd64/最终制品仍待完成。原 48 项状态保持，S2-03 仍 partial/in_progress；主观批阅具体提案尚待授权，本轮未实现其原生答案或采用写入。
