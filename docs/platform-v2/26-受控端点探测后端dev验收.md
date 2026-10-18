# 受控端点探测后端 dev 验收

2026-10-19，AutoLab `c965a7d` → `d8dfa80` → `4127ca0`，web2 保持 `a82cbee`。承接 [25](25-本人端点用量dev验收.md)，本轮实现探测后端与原 worker 账本链；前端确认、结果轮询和真实供应商探测仍待实施。仅 dev、本地提交，不 push、不改生产、Java、schema、角色、seccomp、镜像或发布链。本轮未调用真实模型。

## 探测合同

| 接口（原 `/auto-task/ai` 前缀） | 行为 |
| --- | --- |
| `GET /ports/{id}/test` | 本人本地报价；不解密 key、访问 DNS/提供商或创建任务。要求 active、有 key、明确价格和当前已批准 release。返回端点/价格版本、最多 3 请求、每请求输入 4096/output 128 token 上限及总预留估价。 |
| `POST /ports/{id}/test` | 本人确认 `version`、`pricing_version`、`max_cost_usd`、`confirmed=true`、`operation_key` 后入原 TaskJob，返回 taskId。费用或版本变化拒绝并要求重读报价；重放原确认不会再调用。 |
| `GET /ports/{id}/test/{taskId}` | 本人查询该端点探测状态和闭合结果投影；不返回 provider 文本、原异常、任务 payload 或 key。暂停账号仍可查修复状态，删除端点仍拒绝。 |

报价上限为 `3 × (4096 × max(input_price, cached_price) + 128 × output_price) / 10^6`，所有价格均来自原确认的本人端点费率。零价必须沿用原明确免费确认，不从“探测”推断免费。端点单任务/月预算及原 runtime 用户/课程预算仍由 `begin_run` 决定，报价不授予预算或槽位。

一次固定 `port.test` 依次发送三种小型 Responses 请求：文本 nonce、`probe_echo` 函数参数、JSON schema 输出。输入由服务器生成，不接受用户 prompt、任意工具、路由或模型地址。函数调用只检查返回参数，不执行模型要求的任何工具或业务操作。这是端点协议诊断，不是新的业务 Agent 组件，不增加 14 组件目录或放开旧模型出口；业务 Agent 仍走 OpenHands SDK/原组件治理。

每项结果为 supported、not_observed 或 unknown，只表示该次固定请求观察到的行为。JSON schema 请求被接受且输出符合本次 schema，不证明提供商严格执行所有 schema；auto tool_choice 未返回所需函数也不能推断模型永远不支持工具。未调用 `/models`，因此 `model_list_supported` 始终 unknown，不能把该 API 当作已完成 models 探测。

## 生命周期与账务

复用原 TaskJob、claim、runtime/task/account 锁、Context/心跳、取消、过期 lease 与原受控 HTTPS egress 子进程。typed admission、claim、执行授权、预留和 canonical complete 均核对原属主/付款主体、固定端点/价格/release 版本；执行中的身份来自原 fresh Java RPC，无 debug 身份旁路，不持久化 Cookie。

每个属主只允许一个未结束探测，每分钟最多 3 个新探测；同 operation 重放不占新次数。每任务 max_attempts=1，失败、崩溃、取消或未知用量都不自动重发。每次 reservation 在原 runtime 锁内验证已有 AiRun 数，不能通过并发或重复 handler 超过三次调用。generic submit 不接受空的伪探测绑定；generic retry 不能复制旧付费确认。

`begin_run/settle_run` 保存三条 BYOK 请求、原 token 预留和费用。缺 usage、超预留或请求异常保留 unsettled，阻止新模型调用；错误不按零费用成功处理。只有三次记录均已结算，且固定内部回执与同 attempt 的三个 run ID 匹配，canonical complete 才写原 `AiPort.capabilities` JSON。调用者省略或替换 apply 回调不能绕过完成检查。探测 JSON 不改端点配置版本，也不作为自动启用其他组件的授权。

初稿按实际 JSON 字节数预留输入。补协议开销反例后发现，usage 3000 虽在用户确认的 4096 内，却会因大于短请求正文而被误判 unsettled。旧 `c965a7d` 产品上新增回归 1 项失败、0.43 秒，保留记录；`4127ca0` 改为每次按已确认的 4096 输入上限预留，原正文仍须不超过 4096 字节。超过 4096 的 usage 仍 unsettled，更小的原 runtime/月预算仍在发送前阻断。

## 验证与逐提交审计

- `c965a7d` 根定向 83 项通过、4.32 秒；独立 exact archive 105 项通过、3.98 秒，另 17 项边界通过、2.17 秒，其中 5 项使用真实随机自有 MySQL，检查同 operation 并发只产生一条任务、旧 RR/已加载身份下停用/版本/费率撤销，以及准入后停用不能 claim。模型和身份为替身，不冒充 Gateway 或真实提供商。
- 预审另保留初始不可变快照的 86 项和 6 项生命周期反例；它们不是最终 commit 的测试数量。独立验证包含调用中撤权、换 key 版本、取消、超额 usage、固定结果投影和完成回调不能旁路。
- `d8dfa80` 实际 Gateway 定向 1 项通过、1.76 秒；独立 exact archive 1 项通过、2.14 秒。原 Java 创建专用临时普通 USER、登录/退出/删除；该用户读取报价、确认、幂等重放，原 fresh RPC 与 `worker.run_once()` 完成原 MySQL/Redis/AiRun 链，另经原用量接口核对三条完整记录。superadmin 不能读取其端点或探测详情。只有 Responses transport 为合成数据；这不是 Linux daemon、浏览器或真实供应商验收。
- `4127ca0` 根最终定向 84 项通过、4.24 秒；独立 exact archive 85 项通过、5.01 秒（额外包含 port_accounting_mysql），另 8 项边界通过。包括 4096/128 三次预留累计等于报价、4097 首次 unsettled、低 runtime/月预算零请求、免费仍预留 token，以及缓存单价高于输入时的保守预留。独立旧开销反例 1 项失败、0.50 秒。
- 最终 clean `4127ca0` 完整 `pytest tests`：1038 通过、23 跳过、0 失败，88.15 秒，父进程退出 0。真实 SDK 解释器和随机自有 MySQL 已启用；本功能定向模型/RPC 使用替身，Gateway 测试在全量默认跳过、另行 opt-in 验证。较早等价 `c965a7d` 工作树完整回归为 1037/22、87.78 秒，仅为此前检查点，未回填为最终版本。

三笔提交均独立 accepted，原失败/预审/修复记录保留。临时 USER 已通过原 Java 删除，5005 已释放；没有重配原 dev 服务或改真实凭据。

本机仓库外 `platform-v2-implementation-20261018` 保存 `port-probe-{initial,backend,backend-projection,full-sdk-mysql,backend-reservation,final-full-sdk-mysql}.log`、`gateway-port-probe.log`、`port-probe-reservation-before.log`、`audit-port-probe-{preflight,backend,gateway,reservation}.*` 及监控记录。20 份明确命名日志/报告对测试 key、dev 密码、RPC token、MySQL/Redis 密码扫描，0 命中；扫描范围不包含工具输出，不使用宽泛配置文件 glob。

## 下一步

本检查点之后，前端报价确认、精确重试、轮询/取消、本人历史与版本提示，以及已授权免费端点的有界真实提供商验收已见 [27](27-端点探测前端与真实供应商dev验收.md)；本页上述历史后端结果保持原样。后续仍需受控 models 探测、脱敏运营视图、剩余 12 组件、原生 MySQL 锁矩阵与最终平台制品；原 48 项不因本链通过而改 done。
