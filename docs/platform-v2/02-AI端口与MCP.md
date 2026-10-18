# 02 AI 端口与 MCP

> 用户自建 Responses 端口、默认端口、持久队列与预算，以及按原权限执行的受限工具。当前 provider/ModelProxy/账户准入继续复用；端口、MCP 和自动委托是新提案，需 [09](09-审计与实施门禁.md) 的审批与验收。

## 1. 产品边界

- v2 不提供隐式模型服务。解析：任务显式端口 → 本人 active 默认端口 → 503 port_not_configured；显式错误端口直接失败，不能换成站点端口。
- 原站点 settings 仅保留给兼容旧任务。切换时显式迁移配置/密钥、说明付费主体、保持可回退；不能给所有新用户自动选择站点 provider。
- 所有 AI 功能需有效端口；JPlag、本地文档提取、材料渲染等确定性任务无需模型。可选 AI 解释失败时仍提供确定性结果并标记解释不可用。
- 模型 ID 由用户填写和能力探测确认；不列假定存在的产品型号，不由服务端猜模型。
- 普通用户可管理本人端口，但不因此获得题库编辑、考试发布或管理 API 权限。

## 2. 端口模型与默认约束

DDL 唯一来源为 [06](06-数据库变更汇总.md)。v1 端口均为本人所有，站点共享能力不在默认解析中。

| 字段 | 行为 |
| --- | --- |
| owner_id / id | 由服务端主体与生成器指定，客户端不能替换归属 |
| base_url / model / wire_api | HTTPS Responses；能力差异按端口记录，不宣称所有 provider 等价 |
| api_key_cipher | 受控密钥加密；不出现在列表、日志、事件、任务快照或 harness 环境 |
| key_fingerprint / has_key | 显示不可逆摘要和“已配置”，不是原 key 的尾号或伪装 key |
| harness / release_id | 从批准 registry 选择，不接任意二进制或版本路径 |
| max_concurrency | [1,32] 只是提议范围，还受站点与用户上限约束 |
| max_job_cost_usd / monthly_budget_usd | 非负 Decimal；零代表不限时须显式确认，不能默认为不限 |
| version / status | CAS 更新，active/disabled/invalid/deleted；禁用默认端口同时清默认 |

**默认唯一范围是每用户，而非全站。** 多个非默认端口应始终可共存。用 nullable generated default_owner_id 的唯一索引保证至多一个 active 默认；事务先锁原 AiAccount 的稳定行，再清旧默认并设置目标。零端口并发创建也受同一行锁保护。CAS、禁用、删除与替换默认使用一致锁顺序。

创建首个端口不隐式设默认；删除/禁用默认后无默认，UI 引导用户选择，不自动挑备用。唯一索引只保证“至多一个”，不要求一直有默认。

## 3. 请求、加密与连通性探测

```json
{
  "name": "我的模型端口",
  "base_url": "https://provider.example/v1",
  "api_key": "<provider-key>",
  "model": "<provider-model-id>",
  "wire_api": "responses",
  "harness": "codex",
  "release_id": "<approved-release>",
  "max_concurrency": 2,
  "max_job_cost_usd": "2.000000000",
  "monthly_budget_usd": "20.000000000",
  "is_default": false
}
```

编辑 key 留空表示不修改，但改变 endpoint 时必须重新提供 key；仅改 model 是否需要换 key 由 provider 能力决定，不能前后端各自猜测。version 必填；同名/并发更新/默认替换的 409 提供明确错误子码。

### 3.1 SSRF 与出口

- 禁止 userinfo/query/fragment；限制 scheme/port、规范化主机、IPv4/IPv6 与编码形式。
- DNS 的全部结果必须排除回环、私网、link-local、元数据等地址；实际连接仍经固定出口策略，防止 DNS rebinding 与解析/连接竞态。
- 禁止重定向，不使用环境代理绕过出口限制；TLS 证书验证、超时、响应字节数、压缩展开与连接数均有限额。
- URL 字符串检查、禁用 redirect 与出口代理是多层约束，不能把前两者之一当作完整 SSRF 防护。
- 回环调试只在隔离开发配置开启；生产用户不能借“调试模式”连接内部模型地址。

### 3.2 探测语义

`GET /models` 可能不被 Responses 兼容服务实现。区分 reachable、model_list_supported、responses_supported 与 unknown；不把 /models 404 当成 Responses 不可用，也不把其成功当成可运行工具/流式请求。

低成本 Responses 探测也可能计费，必须先显示费用/令牌上限并走原逐请求预留和结算。只返回状态、延迟和脱敏错误子码，不回传 provider 响应体。探测受属主权限和限频控制。

## 4. 队列、额度与预算

入队时解析并固定 port_id、port_version、model、release_id、价格版本、预算上限与输入 manifest；旧任务和重试不能静默改用用户后来设置的默认端口。配置改变时旧 secret 不能自动送往新 endpoint；旧 key 版本若不能安全保留则任务明确 blocked，重新授权/创建新作业。

### 4.1 claim 与容量

在原 TaskJob claim/runtime_lock 事务中增加端口容量，并检查全局、用户、通道、节点额度。active 是 DB 权威事实；SKIP LOCKED 负责候选扫描，不单独保证配额。不同端口继续扫描，不被某一端口的队首阻塞。

仅 AI 请求需要 port；NON_AI 通道保持原语义。领取、释放、租约过期、取消、禁用端口与 stale worker 完成均需真实 MySQL 多进程反例。端口禁用后撤销新模型请求和工具授权，在途请求进入结算/对账，不能直接抹掉费用。

### 4.2 计费

复用 AiRun/AiLedger/ModelProxy 的逐请求预留、usage 校验、幂等结算与 unsettled 冻结。AiRun 增加可查询的 port_id 维度；不能只新增预算字段而没有账本实现。

- 锁定计费主体/端口后，按已结算 + 在途预留判定月预算，月份使用明确 UTC 周期。
- input/output/cache 和长上下文费率按完整合法区间保守预留；未知或未批准的价格在发送前 blocked，先补齐获准费率，不能先请求再对账。只有已经发送且 usage 缺失、断流等无法确认费用的请求进入 unsettled，不按零费用成功结算。
- 单请求/作业/月份额度分别核验，不能因单次 LLM 请求低于上限就让多轮累计越界。
- 原平台积分与自有端口 provider 费用分账展示；模型服务最终账单不由本系统凭空保证精确。价格版本、余量与超支边界需可解释。
- 探测、重试、断流、取消、缓存 usage 和重复完成均计入同一账本链。

| 情形 | 行为 |
| --- | --- |
| 并发已满 | pending，展示原因；不是创建请求的 429 |
| 队列/频率上限 | 拒绝创建，429 |
| 预算耗尽 | blocked，人工调整或新授权后再恢复 |
| invalid/disabled/配置版本不可用 | blocked，不切备用端口 |
| 会话/委托撤销 | 停止新调用并保留可对账状态 |
| 确定性非 AI 作业 | 不要求端口，不因 provider 缺失失败 |

## 5. MCP 与原身份边界

### 5.1 先保留正确的已有模式

reviewed 管理 Agent 通过持久动作请求和当前浏览器确认执行 OJ 操作。Cookie 不进入 job payload、数据库或模型 prompt。v1 抽象不改变这一点。

自动 MCP 授权是新增能力，不得直接把 owner_id 填入 SDUOJUserInfo 后用全能内部 token 调用，也不得把内部 RPC 权限等同于代表用户的业务权限。

### 5.2 自动调用的前置设计

作业令牌绑定 subject、job/execution/lease、audience、工具列表、资源范围、授权版本、过期时间和可撤销 grant；签名或高熵 opaque token 均需服务端验证，不能仅相信客户端参数。

每次调用重新验证当前主体、原会话或获准委托、角色/组/资源权限及当前 lease。对于写操作，还校验参数 hash、目标版本、审批记录与幂等键。权限撤销后新操作立即失效；旧确认和 ABA 往返不能恢复失效动作。

MCP token 与模型代理 token、Java RPC token 完全分离，不透传给下游。若还没有经批准的用户委托验证入口，保留浏览器确认，不发布自动写能力。

### 5.3 协议

选择 MCP 2025-11-25 规范快照作为互操作设计依据，实际 SDK/harness 版本由契约测试固定；不宣称这就是最新版本。

```text
initialize / initialized -> tools/list -> tools/call
业务输出 -> CallToolResult {content, structuredContent?, isError}
格式/未知工具 -> JSON-RPC 协议错误
业务拒绝 -> isError=true + 脱敏错误与可读说明
```

内部业务结构 `{ok,data,error}` 可放 structuredContent，并在 content text 中提供兼容形式；不能直接用它替换 MCP 协议结果。定义 inputSchema/outputSchema、大小上限和 additionalProperties=false。tools/list 也按权限裁剪。

Codex 当前 dynamicTools 由适配器映射到同一 Broker；DSH MCP 能力待 S2-07 验证，不能预先写“两者都能挂 MCP”。参考 [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) 与[安全建议](https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices)。

### 5.4 工具、风险与审批

| 工具 | 级别 | 必须满足 |
| --- | --- | --- |
| oj.user.profile、problem.search/get | L0 | 当前身份和字段裁剪，公开题面不含隐藏答案/测试数据 |
| oj.exam.list/get、submission.list | L0 敏感读 | 对象/场次权限、本人代码和考生信息最小投影；首次数据授权 |
| oj.problem.upload_testcase | L2 | 上传也可覆盖/污染题目，不按低危自动放行；大小/目标/版本校验 |
| oj.problem.set_checkpoints、update_description、create | L2 | 逐次确认、源权限、版本与幂等 |
| oj.group.add_members | L3 | 会改变访问权限，逐次确认目标组与人员清单 |
| oj.exam.prepare/publish、seat.assign、查重写回 | L3 | 保留原 TEST/FORMAL 门禁、目标版本与二次确认 |
| oj.plagiarism.scan | L2 | 固定范围与成本，发布/写回另行 L3，不能一次请求隐含执行 |

只读并非天然安全，提示词不可信。拒绝任意 SQL、任意 HTTP、任意路径和权限提升工具。被拒的参数不能经别名工具绕过。审批绑定一次副作用，不把“同参数记住”当作重复写的永久批准。

### 5.5 审计与未知结果

审计表保留 subject、grant、job/lease、call_id、工具和参数摘要、resource_version、审批人、时间、result_code 和外部 receipt。唯一 execution+call_id 防重放；不记录 key/Cookie/原始密码。

对外写入采用 pending→approved→executing→completed/failed/unknown；HTTP 超时不自动重发。unknown 状态要先读回对账或人工处置。DB 事务无法撤销已经成功的外部 OJ 操作。

## 6. 旧主观题批阅迁移

现有实现已有 AiReview/草稿和教师 adopt 语义，不是“旧批阅无审核”。新实现只替换受控模型执行部分，保持评分 schema、证据、资源版本与教师确认后写成绩的边界。

双跑只产生隔离草稿，不重复扣分或重复采用，不把学生全部答案发往未获准端口。验收集与评分偏差阈值须由教师在运行前确认；差异、unknown、成本和人工采用结果均入报告。legacy/agent 开关保持一个兼容期；TaskJob 旧任务按冻结输入完成或明确取消，不重新路由到新默认端口。

## 7. 提示词与前端实施

保留 base/task 提示词分层，版本与作业输入一同冻结。模型可选择工具顺序，但权限、schema、预算、幂等、版本、发布门禁与人工审批始终是服务端硬约束，不用提示词替代。

用户端口页使用登录用户布局；管理端只展示经授权的全站脱敏运营信息。密钥字段编辑不回显，摘要标“指纹”；费用确认、默认替换、未配置引导、排队原因、unsettled 与重试行为见 [08](08-前端改造方案.md)。路径以 [07](07-API清单.md) 为准。

实施：端口数据约束 → CRUD/SSRF/探测 → 入队快照和预算 → 原队列容量 → Harness/Broker 契约 → 经批准的委托和工具 → 批阅兼容。未过 AUTH/SANDBOX 时保留原人工管理能力，不向公开用户放开后台 Agent。
