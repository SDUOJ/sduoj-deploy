# 01 基于 OpenHands 的 AutoLab Agent 执行

> 最新决策以 [10](10-OpenHands与Agent组件.md) 为准：OpenHands Software Agent SDK + 原 AutoLab Task worker + 用户端点。AI 平台实现归 AutoLab；Java 保留业务权威与既有接口。一期不建设独立云 Agent 平台或多 Harness 调度器。

## 1. 已有基础与新增工作

| 项 | reviewed 基线 | 本次实施 |
| --- | --- | --- |
| 业务会话 | AiResource 保存管理/业务资源、事件、待确认动作 | 继续作为业务权威，关联 OpenHands conversation/checkpoint |
| 异步执行 | TaskJob + auto_task.worker，claim/心跳/lease/fenced complete | worker 加组件 dispatcher 和 OpenHands SDK adapter |
| 当前引擎 | 管理助手和部分模型链使用 Codex 适配 | 分组件迁移到 OpenHands，不把旧代码标为已经迁移 |
| 模型调用 | ModelProxy/AiRun 逐请求准入与结算 | 用户端点固定到任务，覆盖 SDK 重试/辅助调用 |
| 当前浏览器确认 | Cookie 仅用于当次确认，动作/receipt 持久化 | 保留；不能让模型直接获得用户会话或内部 RPC token |
| 执行工具 | 原 sandbox.py 支持受控命令子任务 | 按 profile 验证；不能直接给 SDK 注册宿主 Terminal/FileEditor |

16 个 Web worker 与 Task worker 是不同概念。Agent 只由领取该任务的 Task worker 调起；Web 请求只提交/查询，Redis 只唤醒，不增加另一套进程内任务权威。

## 2. 一次任务的生命周期

```text
用户输入 / 某组件 action
  -> AutoLab：开关 + 主体/源对象权限 + 本人端点/预算
  -> 原 TaskJob / TaskInput：冻结组件、版本、端点和输入
  -> auto_task.worker：claim / heartbeat / Context
  -> 组件 dispatcher -> OpenHands SDK Agent / Conversation
     -> ModelProxy -> 用户实际端点
     -> 受限 AutoLab 工具 / 经批准的隔离执行工具
  -> 原日志与候选结果 -> fenced complete / 用量结算
```

一次 turn 一个 TaskJob，多次模型调用共享任务预算。同一会话串行变更；下个 turn 是新 TaskJob，不能让一个交互会话长期占满 worker。新的统一入口用 agent.run，旧 task_type/API 通过固定映射分批迁移；旧批量、串联、重试和确认也必须经过组件/action gating。

组件不是任意 Python 插件安装器。服务端登记 id/version、action、工具、输入输出 schema、执行 profile 与上限；前端/M 端只选择已安装且允许的能力。机器目录、开关语义和 13 个组件见 [10](10-OpenHands与Agent组件.md) 及 [清单](agent-components.yaml)。

### 2.1 人工确认与恢复

一期 propose_action 生成候选后结束当前 turn，原任务可 success、结果 requires_confirmation。本人在有效浏览器会话确认，保存 receipt，需要继续再创建 turn。等待期间不占 worker，不持久化 Cookie；不是把浏览器确认值直接传给模型当作授权。

发布/写成绩/创建账号等外部动作若结果未知，先读回对账；max_attempts、旧 lease、组件版本和资源版本共同约束恢复。不能用 SDK checkpoint、VM 快照或保存了 conversation_id 宣称外部 exactly-once。旧版确认在关闭/撤权/ABA 后不得复活。

## 3. SDK 与执行位置

[OpenHands 架构](https://docs.openhands.dev/sdk/arch/overview)提供 SDK、工具、工作区与可选 Agent Server 的边界。SDUOJ 选自己的前端/业务 API/Task worker，Agent Canvas 和其调度不作为一期依赖。

- **business_tools**：worker 内运行可信 SDK 循环，只装本组件经审核的业务工具。模型只能提交结构化数据或动作建议；不得执行宿主 shell、任意路径/HTTP/SQL。读取/写入仍由原业务权限与工具 schema 决定。
- **sandbox_tools**：不可信代码、通用终端与文件工具只能在任务专属隔离工作区执行。worker 负责生命周期；若 SDK 将循环放在沙箱内 Agent Server，必须记录实际进程位置、网络和凭据路径，不能把“worker 调起”误写为所有代码都在宿主执行。
- PoC 固定 SDK/release/依赖和接口样本，不从 main/版本号猜兼容。已读取的 SDK Python >=3.12 要求须与 AutoLab 环境核对，不能顺带升级其它业务依赖或改原供应链。
- 接入第二种外部 Harness 是以后独立需求；早稿 Codex/DSH 对比只作历史证据，不再阻塞当前 OpenHands 交付。

## 4. 隔离和网络合同

正式提交继续使用原 judger/sduoj-sandbox 与发布链，不把判题沙箱修改为通用 Agent 平台。

| 边界 | 要求 |
| --- | --- |
| 执行 | 不可信程序非 root、cap-drop、no-new-privileges，CPU/内存/进程/磁盘/输出和时长有限额 |
| 文件 | 一作业/attempt 独立可写目录；只读输入，不挂 Docker socket、宿主工作目录、其它租户目录和真实配置 |
| 网络 | 非可信工作区默认拒绝出网/内网；仅允许经核准的模型代理和工具中继，实测 DNS/IP/IPv6/redirect/元数据旁路 |
| 凭据 | SDK/工作区只获得 task/attempt/lease 绑定短期能力；provider key、Cookie、内部 RPC token、长期 S3 key 留在可信侧 |
| 控制 | 能力/开关/权限丢失停止新调用；取消只作用于本任务所拥有的进程和环境 |

network none 与 HTTP 模型访问不能同时凭空成立；采用受控 stdio/socket 中继或实际受限代理 profile。引入 OpenSandbox/E2B 等执行后端是 AutoLab adapter 后面的部署选择，须独立验证并遵循原发布规范，不新增面向用户的 Agent 平台。

## 5. 工作区、持久化和版本

工作区优先任务专用本地卷 + 不可变输入/产物清单 + 显式对象上传。S3 FUSE 不是先决条件；[s3fs 限制](https://github.com/s3fs-fuse/s3fs-fuse#limitations)也不支持把 bucket 直接当跨节点会话数据库。

```text
tenants/<tenant>/agent-workspace/<job>/inputs/<manifest_sha>/
tenants/<tenant>/agent-workspace/<job>/attempts/<attempt>/artifacts/
tenants/<tenant>/agent-workspace/<job>/checkpoints/<checkpoint_id>/
```

其余 problem-asset/exam-material/plagiarism-report/submission-archive 目录仍按原领域约定。tenant 由服务端主体推导；只有清单、字节数和 hash 验证/登记完成的对象才是成功产物。checkpoint 不保存可重用凭据，恢复时重新授权，不复活旧批准。

TaskJob、AiResource、AiRun 与原日志足以承载一期业务/配置引用；不能为 SDK 复制一套任务、账本或正文。06 中 auto_agent_node/session/execution 等是早稿保留的扩展评审对象，**不作为一期必须建表的依赖**。需要新增列或迁移时先按实际适配结果提出最小 SCHEMA 提案。

组件与 SDK 的精确 release、输入/输出/checkpoint schema 一起冻结。在途任务固定旧版本，新任务才用新 release；未排空禁止卸载，旧数据/账本和必要的 checkpoint 读取能力保留。恢复不了应明确失败，不能自动重新生成/发布。

## 6. 验收和落地顺序

先在隔离环境用假模型 + 真实 SDK 跑通一次 TaskJob，再验用户端点/用量/重试，然后组件开关和 capabilities、分批迁移业务；shell profile 在隔离验证前关闭。详细实施包 OH-01–OH-06 见 10。

验证 worker 不在 Web 中启动模型、跨 worker 幂等/额度、关闭/撤权/旧 lease、SDK 取消/断线/坏结果、真实 MySQL 锁、产物/状态恢复、跨租户文件/凭据、模型代理可达与出口限制。未经测量不宣称启动延迟、吞吐或多节点恢复可用；本轮不表示 SDK/服务集成已通过。
