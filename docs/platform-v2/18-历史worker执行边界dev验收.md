# 历史 worker 执行边界 dev 验收

2026-10-19，承接 [17](17-旧任务入队dev验收.md)。仅 dev 和隔离测试；未 push、未改生产、未调用真实模型，未启用业务组件。

## 提交与行为

| AutoLab 提交 | 范围 |
| --- | --- |
| 15e9f5f | claim 在发 lease、递增 attempt 前阻塞未适配的历史任务，延期 30 秒，清除 lease，保留输入/旧结果/attempt；扫描继续，不让整页旧任务阻塞后面的确定性任务 |
| 089146a | Context.check 拒绝旧模型类型，首次与周期 heartbeat 从持久任务重验适配绑定；完成事务固定选择已登记文档适配器的完成函数，调用者省略或替换回调均不能跳过检查 |
| 9fae53f | test-only：旧进程恢复测试改为实际 typed 准入与真实子进程硬退出，使用随机自有 MySQL 库，修正公共队列 fixture 变为确定性任务后的语义漂移 |
| 4f128b9 | test-only：旧原生授权撤销在 claim 前阻塞；另以已领取的实际 typed 任务验证撤权后失败与释放同 owner 槽位；首次 heartbeat 的反例固定单调时钟起点 |

组件后来启用或关闭再开启都不能复活旧任务类型。旧 worker 过期的运行中 AiRun 仍先转为 unsettled；对账修复账务，不安装旧适配器。原暂停账号的取消处理保留，终态历史不重写。typed agent.run 继续原 queued_binding，不因新拦截而改走旧站点 provider。

首次 heartbeat 使用负无穷初值，避免假定 monotonic 已超过五秒。运行中的实际类型与绑定由持久行决定；原权限刷新、取消和有效 lease 仍检查。新 SDK 的模型/工具入口继续逐请求 fresh 权限校验，heartbeat 重核策略、来源版本与端点等冻结元数据；两者不能混为同一种校验。

续租和完成沿用 runtime→task 锁序。旧模型完成不能调用 apply 或写入 success/result/log；有效旧 lease 也不例外。新文档 Agent 的完成固定调用 complete_translation，校验当前原来源权限、策略/端点绑定、结算状态及候选关联，再写 awaiting_confirmation。手工候选采用仍是另一次浏览器事务。NON_AI 的原结果回调保留；取消、失败清理和账务对账继续使用原 fenced primitive，不因执行被禁用而无法清理。

## 验证与独立审计

- 15e9f5f：组合回归 204 通过、1 跳过；最后完善开关 ABA 的专用套件 28 通过。真实随机自有 loopback MySQL 双线程、110 个旧任务、同 owner 排队及全局限制两项通过。独立 exact SHA 审计接受：204 通过、1 跳过，真实 MySQL 两项及外置两项反例通过。
- 089146a：主测 226 通过、1 跳过；真实 SDK 进程＋worker＋隔离 MySQL＋假供应商链 5 通过、2 个真实供应商用例明确未启用。独立 exact SHA 审计接受：265 通过、1 跳过，真实 SDK/MySQL 5 通过、2 跳过，外置三项反例通过。
- 9fae53f：主测 1 通过，独立 exact SHA 1 通过、1.17 秒，审计接受。实际顺序为 typed API→子进程 claim/current_scope→持久 AiRun 预留→os._exit(99)→人工将 lease 时间写为过去→unsettled/blocked，attempt 保持 1；没有 HTTP/模型调用，不宣称这是 SDK 推理成功或真实等待 lease 到期。
- 4f128b9：主测 61 通过，独立 exact SHA 61 通过、1.71 秒，审计接受。仅 worker 领取后交接由固定旧 lease fixture 模拟；实际 typed 准入、权限函数、失败写入和后续同 owner 任务领取均执行，没有替换 queued_binding。

完整 SDK/MySQL 回归在 4f128b9：923 通过、17 跳过、0 失败，81.24 秒。17 项为本轮明确未启用的真实供应商两项、本地容器/真实 authoring 十项，以及依赖旧固定库配置的 MySQL/锁测试五项，均不能计为已验收。不将上述组合数量相加替代这份全量结果。原始中间失败日志保留，包括六项旧领取预期、首次 heartbeat 时钟问题、结果 None 的断言修订，以及上一份完整回归的旧 native worker 领取预期失败。

本轮将原先未启用的 MySQL/SDK 测试纳入组合；真实身份 RPC 和 Responses 供应商仍为 fixture。真实供应商、本地容器以及依赖旧固定命名 MySQL 配置的用例另列未运行，不以 SQLite 或假供应商替代其验收。

证据保存在当前任务的 work/platform-v2-implementation-20261018：legacy-claim-*.log、worker-completion-*.log、typed-process-recovery-mysql.log、typed-worker-revocation-regression.log、worker-boundary-full-sdk-mysql*.log，以及 audit-legacy-task-claim、audit-worker-completion-binding、audit-typed-process-recovery、audit-typed-worker-revocation 的 md/json 和独立日志。

## 下一步

旧候选的审阅、原生评分采用与 AI 出题候选发布仍需按当前适配器与来源绑定限制；原手工题库、Java 手工管理和确定性考务/查重维护须保留。继续补真实网关/身份 RPC/Redis、Linux 安装、浏览器和取消恢复的完整业务验收，然后逐组件迁移。INSTALLED_COMPONENTS 仍为空，48 项任务不标 done，当前不能启用为发布候选。

后续旧候选审阅、原生评分采用和出题发布的实现、初始审计反例与修复见 [19](19-旧候选采用与发布dev验收.md)；本文中的相关待办保留为当时检查点，不表示后续仍未处理。
