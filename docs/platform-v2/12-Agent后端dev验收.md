# 首个 Agent 后端的 dev 验收

这是第一阶段后端增量，设计基准仍为 [10](10-OpenHands与Agent组件.md)，实际进度见 [11](11-dev实施进度.md)。不改 Java、生产、镜像或发布流程，不 push。组件安装集仍为空；以下入口只用于隔离合同测试，不能通过改数据库开关绕过未完成的安装条件。

## 已连接的业务范围

普通纯文本文档翻译：一次 `agent.run` 任务由原 Task worker 管理，先执行内容审核，再执行翻译 SDK 阶段。只暴露对应作用域读取和提候选工具；不读取宿主文件、启动 shell、加载 MCP/skills 或自动写 Java。

服务端冻结原文快照/hash、组件及依赖代次、本人端点/模型/release/价格版本。claim 检查持久绑定；worker 在执行前用原 fresh Java 身份 RPC 验证当前主体，并在模型预留、工具及完成处重核原权限。文档父课程/题单和账户状态采用当前锁读，不能由旧 RR 视图恢复已撤销权限。

模型请求经过原 ModelProxy/AiRun：逐请求预留、月预算含在途金额、未知/超预留用量进入 unsettled。BYOK 成本估价保留在原账本，平台积分不重复扣款。key 只在父进程和单次 egress 私有管道中使用，SDK 得到临时 loopback token；出口子进程有父侧总期限和自身内核期限。

SDK 结束后先关闭代理并等待已准入的模型/工具事务完成；记录失败会终止该 turn，不能再发请求或成功完成任务。成功任务只生成持久候选；人工采用在新浏览器事务中执行，原 running lease 已释放。通用资源详情/历史不能访问候选及采用回执。

## dev 接口合同

均位于原 `/auto-task/ai` 保护前缀，复用当前 Gateway 身份，不接受客户端 owner/角色/冻结策略字段。

| 接口 | 输入与行为 |
| --- | --- |
| `POST /agent/document-translations/create` | `resource_id`、`resource_version`、`language`（zh/en）、可选 `port_id`、`operation_key`；仅当前原管理权限可提交。显式端口失效不回退。 |
| 原 `GET /jobs/{taskId}` | Agent 任务详情仅提交人可读；复用原任务历史/事件。 |
| 原 `POST /jobs/{taskId}/cancel` | 复用原取消、租约 fencing 与未知用量处理。 |
| `GET /agent/candidates/{id}` | 本人及当前原文档权限，读取候选。 |
| `POST /agent/candidates/{id}/adopt` | `version`、`candidate_hash`、`operation_key`、`reason`；原子采用与回执重放。 |

采用要求任务成功、attempt 一致、当前策略、源版本/hash、候选 hash/CAS、24 小时有效期和已结算用量。只增加独立译文，保留原文；手工修改原文会清除旧译文。采纳不依赖旧 worker lease，也不会自动重放外部写。

取消/失败后用新的翻译创建请求和 operation key 重新冻结。旧 generic retry 明确拒绝 Agent 任务，避免把旧端口/代次复制到未绑定 harness 的任务。价格未知仍拒绝平台调用。用户于 2026-10-19 明确专用测试 API 免费但有限量，隔离测试仅为该端点显式确认零价；其他端点不能沿用这个确认。

## 验证及剩余范围

- `test_real_sdk_worker_review_translation_and_human_adoption_chain`：实际 ASGI admission、原 worker/claim、两个真实 SDK 进程阶段、六次代理请求、真实 MySQL AiRun、候选和人工采用/重放。提供商和 fresh Java 身份 RPC 是 fake，不是完整真实站点验收。
- runner 和 SDK/worker 测试现会检查模型下一次请求实际收到工具观察值，避免固定步骤的 fake provider 掩盖反馈错误。0bf775c 检查点组合回归为 447 通过、2 跳过（78.47 秒）；后续旧模型出口退役改变测试集合，f856af0 为 439 通过、3 跳过，范围及替代覆盖见 [15](15-旧模型出口dev验收.md)。
- workflow 回归覆盖缺 usage、原审核惩戒、阶段间取消/撤权、显式重新冻结、审核/候选后崩溃与旧 attempt 拒绝；独立审计保留中间失败 SHA，不能把失败旧提交当成已通过。
- MySQL 验证包含端口并发预算、默认/价格旧 RR、配置 CAS、claim、父 ACL 撤销/删除、用量当前读、候选并发采用及回执。原生题目来源锁等尚未覆盖项仍列于 11。
- 早期手动探针只按 finish 和调用名判定通过，实际工具反馈失败；该错误判据和失败记录保留。修正 SDK 具体 observation 类型后，两指定模型各 3 次 Responses 请求通过合成 Hello 测试：父侧读取/提候选成功，后续模型输入收到实际结果，finish 精确匹配临时随机候选回执。与平台 ledger 分开记录，不含真实业务权限/数据；不能外推所有模型、组件或账务验收。

`test_opt_in_free_provider_worker_usage_and_human_adoption` 另经明确 opt-in，对两个专用免费模型验证了真实 SDK/HTTPS/ModelProxy/MySQL AiRun、候选与人工采用/重放，2 项通过，各 6 次模型请求。观察 wrapper 原样转发，不替代提供商；身份 RPC 和安装状态仍是测试替身。初次失败和诊断边界见 11，不据此声称全部稳定。

普通文档候选前端已完成 mock API 隔离验收，见 [14](14-普通文档Agent前端dev验收.md)。尚缺完整旧 AI 入口 gate/迁移、其余业务组件、其他实际端点费率及验收、真实 Gateway/Java RPC/Redis/完整站点浏览器、Linux SDK 安装验证。本人端点页面已有 mock API 浏览器回归，见 13。原 Run、云保存、正式提交和手工功能沿用原流程。

SDK 环境使用独立 Python 3.13，原 Web/worker 保留 Python 3.9/Pydantic 1。worker 通过 `AUTOLAB_OPENHANDS_PYTHON` 指向独立解释器，安装与锁文件见 AutoLab `agent_runner/README.md`。MySQL 测试仅使用校验过的 loopback 配置及随机自有库；不得把 fixture 指向生产或现有业务库。

后续真实 Gateway、Java 身份、自有 MySQL/Redis、SDK 与本人端点隔离的定向验收见 [20](20-真实网关身份与端点dev验收.md)。本文中的旧待验收表述是此前检查点，新的范围和仍未覆盖项以 20 为准。

Linux arm64 子解释器的安装、平台依赖锁和协议验证见 [21](21-Linux子进程dev验收.md)，完整 Linux worker 与其他架构仍未验收。

独立原 worker 的运行中取消/对账/继续执行，以及当前前端走原网关的创建至人工采用链，已补于 [22](22-独立worker与真实浏览器dev验收.md)。这轮模型与安装投影仍 synthetic，不替代完整 Linux 服务或真实供应商浏览器组合。

完整 Linux arm64 worker 的后续定向验收、实际取消死锁及修复、当前后端回归见 [23](23-Linux完整worker与取消锁序dev验收.md)；它不等于完整 Linux Web 站点或最终生产制品验收。
