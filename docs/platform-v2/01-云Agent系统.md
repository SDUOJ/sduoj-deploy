# 01 云 Agent 系统

> 目标：保留既有持久任务与人工审批流程，增加多 harness、隔离 Runner、多节点和 S3 工作区。当前事实以 [09](09-审计与实施门禁.md) 的 reviewed 基线为准；新能力均为设计提案。

## 1. 已有能力与真实缺口

| 项 | reviewed 代码事实 | v2 工作 |
| --- | --- | --- |
| 智能管理会话 | AiResource(kind=management_session) 持久保存事件、动作及当前 task_id | 扩展事件游标和运行位置，不另造进程内权威 |
| 执行 | management.turn 由 TaskJob worker 执行，租约与 max_attempts=1 防止不确定写重放 | 增加 Runner 节点归属、执行 attempt 与 fencing |
| 人工确认 | 当前请求 Cookie 仅在 decide/execute_action 使用，结果持久化；可跨 Web worker 确认 | 保留；自动委托路径另经 AUTH 门禁 |
| 模型准入 | ModelProxy 隔离真实 provider key，逐请求预留与结算 AiRun | 按端口固定配置/价格和额度，不能绕开代理 |
| Harness | 当前实现为 Codex app-server 适配 | 抽离接口，再接经实测的 DSH |
| Docker 执行沙箱 | sandbox.py 给编译/命令子任务加容器限制 | 不等于整个 harness 已隔离，需验证进程、网络和工作区边界 |

旧副本的 RUNTIMES 描述不再作为架构前提。16 个 Web worker 与多节点 Runner 是不同问题；前者已有持久任务方案，后者仍需调度和恢复设计。

## 2. 执行模型

```text
Web/API -> 既有 TaskJob -> claim + 原 runtime 稳定锁
                         -> 节点容量/用户/通道/端口额度
                         -> execution(attempt, lease_token, node_id)
                         -> 隔离 harness
                            |-- 受限模型代理（真实 key 留在服务侧）
                            |-- MCP Broker（工具与资源授权）
                            `-- 作业专用 /work + 只读输入快照
                         -> fenced 完成/失败 + 用量结算 + 产物清单
```

- TaskJob 是唯一任务权威；Redis 只唤醒，不保存并发事实。不要在 Web 进程中另做调度器或可变会话路由。
- Runner 控制面在私有网络/独立监听入口，不经公共 SPA 网关开放。节点身份和 job lease 必须同时验证。
- 节点 heartbeat/in_flight 是观测值，不能据其自报绕过 DB 额度。
- 所有完成、工具副作用和产物登记绑定 attempt/lease_token；租约过期的旧节点不能提交结果。
- 状态和取消延迟都可观察；请求断开不表示后台作业成功取消。

## 3. Harness 契约

```python
class HarnessSpec:
    name: str                  # 从管理员批准的 registry 选择
    release_id: str             # 精确版本 + 二进制/镜像 digest
    protocol_profile: str       # 实测协议配置，不按版本号猜测
    capabilities: dict         # multi_turn, tools, resume, cancel, events

class HarnessSession:
    async def start(self, execution, input_manifest, tools, model_proxy): ...
    async def send(self, turn_id, text): ...
    async def events(self, after_event_id=None): ...
    async def cancel(self, reason): ...
    async def export_checkpoint(self): ...
    async def resume(self, checkpoint): ...
    async def close(self): ...
```

`resume`、`send` 等能力可不支持，必须显式失败；不能用新进程重跑旧提示词来伪装恢复。用户只能选择获准的 release，不能传 binary 路径、环境变量名、任意镜像或 Docker 参数。

事件至少包含 execution_id、turn_id、递增 sequence、kind、data。kind 为 text_delta/message/tool_call/plan/turn_done/error/cancelled。事件去重与有界存储需独立测试，输出大小和日志条数受限。工具调用返回必须关联原 call_id，迟到回复不得送入另一个 turn。

### 3.1 Codex 适配

迁移 reviewed management_agent 的 initialize、thread/start/resume、turn/start 和工具回复代码，保留本地 fake model + 真实 app-server 的原协议回归。原稿记载的 `0.154.0-alpha.6.2` 只能作为历史证据，不能当作今日安装版本或广泛兼容区间。

恢复验收包含 CLI 自身的会话数据库/文件、工作区、配置和权限状态。只保存 thread_id 或把 session_id 放到 S3，不证明另一节点可以 thread/resume。恢复不了则明确失败，不重新执行已确认写动作。

### 3.2 DSH 能力探测（S2-07）

DSH headless 的多轮、结构化事件、MCP、取消及跨节点恢复尚未验证。原稿记录的 CLI 路径和版本只作线索。

探测在临时隔离 profile/工作目录中完成，记录实际版本、digest、完整命令、退出状态和脱敏协议样本；先用假模型和无副作用工具，付费模型另确认费用。不得修改用户真实配置或以 sudo 绕过 profile 权限。

| 能力 | 正向测试 | 反例 |
| --- | --- | --- |
| 多轮 | 第二轮能引用第一轮确定性标记 | 不支持时返回明确 capability error |
| 工具 | 受限工具参数和结果正确往返 | 未列出工具被拒，不能退化成任意 HTTP/shell |
| 结构化事件 | tool_call 与最终结果可区分 | 混入普通 stdout、坏 JSON、缺 final 均不判成功 |
| 取消/超时 | 终止子进程树并释放租约和额度 | 挂起子进程、断线、重复 cancel |
| 恢复 | 新节点+相同输入/checkpoint 成功 | 缺文件/版本变更失败，禁止写重放 |

若只支持单轮，则只能发布 single_turn 能力；调度器多次调用不等同原生多轮。DSH 未通过不阻塞 Codex 路径，不能在文档或 UI 宣称两者等价。

## 4. 隔离与网络

OJ 的 sduoj-sandbox 继续服务正式评测，不把它改成 Agent 执行器。v2 不修改其 JSON/seccomp 或 judger 构建链。

| 边界 | 要求 |
| --- | --- |
| 进程 | 每作业独立沙箱，非 root、no-new-privileges、cap-drop、进程/CPU/内存/磁盘限额 |
| 文件 | 只读根、独立 /tmp 和 /work；不挂宿主目录、Docker socket、其它租户卷、密钥目录 |
| 网络 | 默认无公网/内网访问；只允许指定模型代理/MCP Broker 的必要通道 |
| 凭据 | 不注入 provider 原 key、Cookie、内部 RPC token 或 S3 长期 key；短期代理 token 仅绑定当前执行 |
| 工具 | 模型只请求受限业务工具；shell 与工具返回均为不可信数据，不能据提示词授予新权限 |
| 宿主服务 | FUSE/对象存储凭据在 Runner 受控挂载服务，容器不因挂载获得 privileged 或 CAP_SYS_ADMIN |

`--network none` 与“通过 HTTP 访问模型/MCP”不能同时假定成立：选择受控 stdio/Unix socket 中继，或经批准的独立网络代理，并实测 DNS、IPv4/IPv6、redirect、元数据地址与旁路访问。具体 runtime（runc/gVisor/Firecracker）由 PoC 决定，不先声明隔离合格或可承载公开不可信多租户。

验收至少包含跨租户目录遍历、符号/硬链接、压缩包路径、资源耗尽、进程逃逸、套接字、恶意工具结果与凭据探测。通过有限反例不等于证明绝无逃逸。涉及隔离策略的实际变更先过 SANDBOX/SECRETS 门禁。

## 5. S3 工作区与持久化

### 5.1 语义与选型

Harness 需要普通路径，但不等于必须直接把整个 bucket 当 POSIX 文件系统。保留“对象存储支持标准文件操作”的目标，先比较：

| 路径 | 用途 | 验收关注 |
| --- | --- | --- |
| 作业专用本地卷 + 快照/显式上传 | 可先交付的兼容路径 | 新节点重建、输入不可变、成功登记前上传完整 |
| s3fs/rclone 等挂载 | 必须经 PoC 才开放 | rename、锁、小文件、断网、flush 与多客户端语义 |
| JuiceFS 等独立元数据文件系统 | 多节点共享候选 | 元数据可用性、备份恢复、挂载隔离、具体版本能力 |

[s3fs 官方限制](https://github.com/s3fs-fuse/s3fs-fuse#limitations)指出其缺少原子 rename 和多客户端协调。因此本方案不把“挂载成功”等同于源码仓库、SQLite 或会话数据库可安全共享，也不把 S3 一致性简单描述为所有提供商均最终一致。

### 5.2 唯一目录约定

```text
tenants/<tenant>/agent-workspace/<job_id>/inputs/<manifest_sha>/
tenants/<tenant>/agent-workspace/<job_id>/attempts/<attempt>/artifacts/
tenants/<tenant>/agent-workspace/<job_id>/checkpoints/<checkpoint_id>/
tenants/<tenant>/problem-asset/<uid>/
tenants/<tenant>/exam-material/<exam_id>/<material_version>/
tenants/<tenant>/plagiarism-report/<scan_id>/<revision>/
tenants/<tenant>/submission-archive/<snapshot_id>/
```

- tenant 由认证主体推导，不能信任客户端提供的前缀；授权按作业和前缀限制。
- inputs 在执行前冻结哈希和字节数，只读挂入。工具/用户输入变化产生新 manifest。
- 一个作业同一时刻只有一个有效写租约；不同 attempt 不能写同一可变目录。
- 登记 artifact 前校验大小、媒体类型、相对路径、哈希及上传完成；先上传临时对象，再由 DB 事务提交清单。无对应清单的对象是待回收孤儿，不是成功结果。
- 缓存不能跨租户暴露可写层；checkpoint 不含可重用密钥，不能用 seccomp 声称能够识别文件内容中的秘密。
- 保留/回收按数据分类设置，带 pending-upload、活跃租约及法律/业务保留标记；删除前检查引用。S3 和元数据均需恢复演练。

## 6. 调度、会话与故障恢复

数据模型只在 [06](06-数据库变更汇总.md) 定义。auto_agent_session 是现有 AiResource 的运行位置扩展，不再存第二份独立业务会话；execution 绑定 job、attempt、node、lease。原事件与审批仍由原会话资源承载。

claim 在原 runtime 稳定行锁下检查全局/用户/通道/端口/节点容量，领取与额度变更同事务；新增端口锁保持全路径一致锁顺序。仅在 Web 内统计 active 列表或只依赖 SKIP LOCKED 不保证跨进程额度。

节点定期心跳，过期不立即重放外部副作用。租约到期后：只读、具可验证 checkpoint 的操作可经授权恢复；存在 executing/unknown 的写操作先读回对账，未证明幂等则人工处置。人工确认动作绑定原 call_id、参数 hash、resource_version、subject 和当前 lease。

取消、权限撤销、会话失效后撤销新模型请求和工具授权；在途外部请求可能已生效，记录结果或 unknown。租约 fencing 不能撤销已发出的网络写操作。

## 7. 版本、性能与发布

registry 使用精确 release_id、binary/image digest、协议样本和通过的契约测试 ID。原稿的宽 SemVer 区间与虚构 app-server/1.0、headless/1.0 不作为兼容依据。

启动自检失败则拒绝该版本；灰度期间存量会话继续固定旧 release，新会话才用新 release。checkpoint schema 标版本；回滚必须保留旧二进制与 checkpoint 读能力，不能称会话外置后“天然可回滚”。

PoC 报告记录固定输入、文件数量/大小、并发、冷/热启动 p50/p95、挂载读写、取消延迟和资源回收；未经基准测试不宣称高性能。容量及验收阈值需在部署资源和 S3 实现确定后冻结。

顺序：现有 Codex 回归 → Harness 抽象 → 精确版本契约 → 节点/execution fencing → 工作区 PoC → 隔离验收 → 小范围灰度。DSH 探测可并行，第二适配器仅在能力验收后开放。
