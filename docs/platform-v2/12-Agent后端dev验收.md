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

取消/失败后用新的翻译创建请求和 operation key 重新冻结。旧 generic retry 明确拒绝 Agent 任务，避免把旧端口/代次复制到未绑定 harness 的任务。价格未知仍拒绝平台调用；已授权手动测试端点不等于该端点免费。

## 验证及剩余范围

- `test_agent_workflow_sdk_mysql.py`：实际 ASGI admission、原 worker/claim、两个真实 SDK 进程阶段、六次代理请求、真实 MySQL AiRun、候选和人工采用/重放。提供商和 fresh Java 身份 RPC 是 fake，不是完整真实站点验收。
- workflow 回归覆盖缺 usage、原审核惩戒、阶段间取消/撤权、显式重新冻结、审核/候选后崩溃与旧 attempt 拒绝；独立审计保留中间失败 SHA，不能把失败旧提交当成已通过。
- MySQL 验证包含端口并发预算、默认/价格旧 RR、配置 CAS、claim、父 ACL 撤销/删除、用量当前读、候选并发采用及回执。原生题目来源锁等尚未覆盖项仍列于 11。
- 两个指定模型的真实 SDK 手动协议测试与平台 ledger 分开记录；仅合成文本，没有真实业务权限/数据。测试结果不能外推所有模型或所有组件。

尚缺：本人端点和候选前端、完整旧 AI 入口 gate/迁移、其余业务组件、实际提供商的已知费率与平台内验收、真实 Gateway/Java RPC/Redis/浏览器、Linux SDK 安装验证。原 Run、云保存、正式提交和手工功能沿用原流程。

SDK 环境使用独立 Python 3.13，原 Web/worker 保留 Python 3.9/Pydantic 1。worker 通过 `AUTOLAB_OPENHANDS_PYTHON` 指向独立解释器，安装与锁文件见 AutoLab `agent_runner/README.md`。MySQL 测试仅使用校验过的 loopback 配置及随机自有库；不得把 fixture 指向生产或现有业务库。
