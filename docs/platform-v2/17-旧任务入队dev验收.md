# 旧任务入队 dev 验收

2026-10-19，承接 [16](16-旧管理入口dev验收.md)。仅 dev，本轮无模型调用、push 或生产变更，组件安装集仍为空。

## 提交范围

| AutoLab 提交 | 行为 |
| --- | --- |
| d48419d | 原 add_tasks、rerun_task 和 durable batch 持久化在修改旧任务、日志或状态之前检查服务端任务类型。混合批次全部预检，不允许部分入队；空批次、原身份及确定性任务行为保留 |
| fd51341 | 通用 jobs/create、retry 在原来源与专用业务检查之后拒绝未适配模型；即使使用历史相同 operation key，也不能通过通用创建接口恢复执行。普通文档 agent.run 仅由原 typed API 准入，通用请求不能伪造该类型 |
| f1ca64c | store.submit 在有效身份之后、账号/来源刷新/任务/log/快照/wake 写入之前加入相同限制，覆盖内部识题、访谈、出题等生产者；typed agent.run 保持现有组件、来源、本人端点绑定链 |
| ce80de6 | test-only：维护真实 typed 准入的积分不足等待、补足后 claim 恢复反例，不替换 queued_binding，不创建额外模型请求 |

NON_AI 仅允许 summary_report、ide.execute、exam.plan、course.index、plagiarism.scan、code_similarity 的确定性部分。可选审核、OCR、解释等模型分段仍须适配器，不能因任务位于此集合而恢复旧 provider。手工题库维护、历史读取、取消和账务对账继续遵循原权限。

识题 intake 拒绝后回滚临时 collection、批次预留和任务分配状态；访谈 preflight/回答不保存未入队的会话/回答；原生批阅和编程出题生成不留下新任务或评分写入。私有来源、题组归属、媒体完整性、消息参数等原检查保留，不以组件不可用替代原权限判断。

历史专用接口可能仍将相同请求返回为历史任务重放；该返回不等于重新入队、恢复 lease 或新模型执行。统一历史 claim 和采用限制仍属于下一批工作。

## 测试契约与证据

队列租约、幂等和公平性测试改用确定性任务。历史结果投影、计费、原生来源及协作权限测试通过显式 historical_task/running_history/historical_intake 构造旧记录，不通过当前入队。历史结果测试直接调用 handler/结果函数，不再把 mock Context.ask 配合旧 HTTP 创建描述为可用的新 Agent 全链。历史 reservation 与 native target fixture 仍调用原权限函数，没有全局关闭 gate 或恢复原始模型出口。

- d48419d 主测 148 通过、1 跳过；独立 exact SHA 60 项及外置 8 项通过，审计接受。
- fd51341 主测 175 通过、1 跳过；独立 exact SHA 141 通过、1 跳过，另 4 项权限先于不可用检查的反例通过，审计接受。这些组合有重叠，不相加。
- 共享限制初次迁移回归为 88 失败、147 通过、2 跳过。失败契约及修订日志保留，没有用跳过或全局 bypass 消除失败。
- 完整后端回归 store-contract-full-final.log 为 794 通过、59 跳过、0 失败，49.52 秒。之后补历史原生评分的旧答卷变更参数，两项投影/陈旧来源反例通过；该参数未纳入前述完整回归计数。
- f1ca64c exact 归档独立影响套件及 typed Agent/端点回归 316 通过、5 跳过，25.31 秒；另 10 项外置反例通过，审计接受，包括真实 typed 创建后积分转负时 claim 阻塞、补足后恢复且 payload/attempt 不丢失。此处“真实 typed”指实际 ASGI/准入函数，身份与数据库仍是隔离 fixture，没有真实模型调用。随后 ce80de6 将该积分恢复反例维护进正式测试，typed task suite 20 项通过，1.10 秒。
- 真实随机自有 loopback MySQL current-unsettled 两项通过，0.96 秒；它验证旧 RR 视图下任务/用量当前读与锁冲突，不是完整网关、Redis 或供应商集成。

跳过项仍是未验收项；普通运行未启用真实供应商、SDK 运行环境、隔离 MySQL、容器等 opt-in 配置，不能把完整 pytest 的通过数量当作这些环境全部通过。SQLite 的 Decimal 警告也不作为真实 MySQL 账务精度证据。

工作目录保存 legacy-queue-admission-initial.log、generic-task-admission-initial.log、store-task-admission-contract-transition.log、store-contract-step1/2/3.log、store-contract-full.log、store-contract-full-final.log、store-contract-authoring-collaboration.log、store-contract-stale-grade.log、store-contract-current-usage-mysql.log 和各提交独立审计报告。

## 下一批边界

1. claim 在发 lease/递增 attempt 之前隔离未适配历史任务，不能阻塞后续确定性任务；新 agent.run 继续原 queued_binding。
2. runtime 检查、完成写事务和旧候选采用补当前适配绑定；已有旧结果不能因后来打开组件开关而自动有效。手工、确定性结果需保持独立可用。
3. 继续 Linux 安装、真实 Gateway/身份 RPC/Redis、取消恢复和浏览器全链验收，再按组件推进。当前不标记新组件已安装，不改原 48 项任务为完成，也不作为可上线候选。
