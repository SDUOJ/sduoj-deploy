# 独立 worker 与真实浏览器 dev 验收

2026-10-19 检查点，承接 [20](20-真实网关身份与端点dev验收.md)。本轮仍仅 dev，不 push、不修改生产、Java、发布链或组件安装集。web2 为 `3615267`；AutoLab 的运行中取消测试为 `8629413`，浏览器发现的可启动投影修复为 `5f69f9e`，证据文案修订为 `bc1930c`，浏览器后端 fixture 为 `1d5af82`。

## 真实部分与替代部分

浏览器走现有 webpack 开发配置与原代理：当前前端 → 原 dev Gateway → 当前 AutoLab `main.app` → 原 Java 身份 RPC、自有 MySQL/Redis → 独立原 Task worker → 实际 OpenHands SDK 子进程。浏览器没有拦截或模拟业务 API，也没有使用 authentication dependency override。数据库为每次新建、结束即删除的随机自有测试库；这是 fixture 初始化，不是旧库迁移或备份恢复演练。

模型出口（含 Responses 传输）和两个组件的安装投影使用合成 fixture；本轮不验证公网 DNS/TLS/受控 egress，相关既有证据单独保留。源码 `INSTALLED_COMPONENTS` 仍为空；没有把组件登记为可上线。worker 通过显式测试 bootstrap 替换模型出口，仍调用原 `worker.run()`，保留原 claim、租约、fresh 身份、用量、候选和取消。宿主是 macOS；Linux 子解释器证据另见 [21](21-Linux子进程dev验收.md)，不能拼接为完整 Linux worker 或生产镜像验收。

专用测试 API 已获免费试用授权，但本轮没有真实供应商请求；前述真实供应商证据仍以 [12](12-Agent后端dev验收.md) 为准。合成暂停请求的已知零用量，不代表真实供应商取消一定免费。

## 独立 worker：运行中取消、对账、继续执行

`8629413` 新增 opt-in Gateway 集成测试和仅测试 bootstrap：

1. 经真实 HTTP 配置两组件策略，创建普通文档和本人端点。
2. 启动独立原 worker，观察 Redis 唤醒订阅增加。首次任务在实际 SDK 已调用合成出口后暂停，观察真实子进程 PID。
3. HTTP 取消后，SDK 子进程在 fixture 清理前退出；worker 同一 PID 仍运行，任务 cancelled/attempt=1，无候选。
4. 未知用量暂为 unsettled，新准入返回 409。此处合成出口确实未产出任何 token，管理员按已知零用量对账；同操作重放成立。
5. 显式新建另一任务，仍由同一 worker 执行六次 SDK 模型步骤，成功后人工采用。数据库核对六条 success AiRun、一条 reconciled AiRun、原文档版本 2 与独立译文。
6. SIGTERM 正常退出 0，fresh 身份 RPC 调用数大于零，Redis 订阅恢复基线。

主验收 1 项通过，13.75 秒；独立审计另跑 1 项通过，13.31 秒，并验证未 opt-in、非自有数据库、非规范合成出口三项启动拒绝。首次主运行的 HTTP 轮询过密触发原网关 429，日志保留；测试改为与前端相同的 2 秒间隔，未改产品限流。

## 浏览器发现并修复的阻塞

首次真实 UI 流程完成新增本人端点和设为默认，但创建翻译按钮一直禁用。实际 capabilities 响应将全部 `can_start` 固定为 false，尚未接入已存在的本人端点适配器。这是产品缺口，不是模型或浏览器测试失败。初轮 harness 按停止指令清理后，因没有采用结果而 1 项失败，421.84 秒；保留该日志。

`5f69f9e` 只为已实现的普通文档翻译投影可启动提示：原 admin 要求、当前来源 write ACL、非 native 且 UTF-8 正文不超过 100000 字节、总/组件/action/依赖/安装门禁，以及至少一个 active、已配置密钥、本人确认价格的本人端点。缺上下文或不支持的来源保持关闭。其他未适配组件不因此可启动。

“至少一个本人端点”表示 UI 可供显式选择；前端仍要求精确匹配本人默认或显式选中端点。没有默认时不自动选择其他端点；typed admission 仍独立重验 ACL、端点、策略、冻结和预算。能力 GET 不解密密钥、不查 DNS、不调用模型、不修改源/任务/配置；原 `get_resource` 的账户初始化、用户名同步和锁行为仍保留，不能宣称所有 SQL 都只读或无锁。

定向回归 44 项通过，1.65 秒；独立复跑 44 项通过，1.73 秒，另有两项独立探针验证不 DNS/解密/模型调用和原账户同步行为。`5f69f9e` 的初始 docstring 误写“无写入、无锁”，审计保留 needs_fix；`bc1930c` 只修正文案与测试注释，独立检查功能 AST 未变后 accepted。

## 真实 UI 正向链

新建独立 fixture 后，以本轮独立 Chromium 会话、现有专用 dev 账户完成：

- 未登录访问本人端点页，正确显示登录提示。
- 通过原登录接口取得私有会话，认证状态仅从仓库外 0600 文件导入，不把密码放入 CLI 参数或日志；结束后删除该临时状态文件。
- UI 新增本人端点，显式填写三项零价并勾选免费确认。保存后只展示密钥摘要，未回显原值；localStorage/sessionStorage 检查不含测试密钥。
- 本轮成功任务的端点没有设为默认。文档页的默认选项保持创建禁用，显式选择刚创建的本人端点后才可点击。
- 点击创建，经实际 Gateway 返回任务 ID；页面自主轮询，先显示正在执行，后显示完成和候选。
- 点击采用，弹窗要求人工勾选和说明；确认后重读来源，显示版本 2、保留原文与已保存译文。候选不再出现可重复采用按钮。
- 1280px 桌面和 390px 窄屏保存截图并目视检查；390px 时 `scrollWidth === innerWidth === 390`。这不是移动设备或全站浏览器兼容性验收。

控制器发出停止后，fixture 从真实数据库确认一个成功任务、六条成功 AiRun、源版本 2 和预期译文；worker 正常退出 0、Redis 订阅恢复。主验收 1 项通过，305.74 秒，包含等待浏览器操作的时间。成功操作后的页面控制台为 0 errors，保留原开发依赖的 5 warnings；webpack 编译无 TypeScript 错误，两个 warning 均为包体积提示。

## 当前树组合回归

AutoLab `1d5af82` 完整 `pytest tests` 在真实随机自有 MySQL 和真实 SDK 解释器下 994 项通过、21 项跳过、0 失败，85.55 秒，父进程退出 0。跳过分为真实提供商 2、authoring 专用集成 1、固定 MySQL 锁 1、容器 9、专用 schema 数据库 3、显式 Gateway 验收 5；这五项另有 20/本页的 opt-in 定向证据，不能改写为本次全量已运行。浏览器 harness 的文件名不匹配默认收集，只显式运行。

初轮全量 1 失败、993 通过、21 跳过，87.10 秒，退出 1；失败是外部启动脚本将集成 MySQL 端口全局注入，与既有 debug 默认端口测试冲突。只修正仓库外启动脚本，使全局 debug 保持原默认、真实 MySQL 仅由专用 fixture 配置，再重跑同一代码树；没有修改产品配置或放宽测试。两份日志均保留。

## 证据与未完成项

本机仓库外 `platform-v2-implementation-20261018` 保存：`gateway-standalone-worker-{initial,fixed}.log`、`audit-standalone-worker-gateway.*`、`gateway-browser-harness{,-fixed}.log`、`browser-harness-fixed-20261019/result.json`、`browser-cli-records/`、`audit-document-readiness*` 与 `audit-browser-harness.*`。web2 的忽略目录 `output/playwright/` 保存 `platform-v2-document-{candidate,adopted,mobile-top}.png`。这些含本机验收细节，不加入源码或公共产品文档。

仍需完整 Linux worker/amd64、真实供应商与浏览器组合、原生题目锁竞争和剩余组件迁移。运行中取消已有本轮独立 worker 证据，未把它说成浏览器点击取消已验收。48 项任务状态不因此改 done；所有实际安装、受控探测、运营视图及原发布门禁仍要分别完成。
